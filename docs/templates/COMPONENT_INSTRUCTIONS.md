# Component Development Instructions

## Purpose
Create React components that can be dynamically loaded and controlled by AG2 agents through the transport system.

## Component Types

### 1. Inline Components
**Location**: `workflows/{WorkflowName}/Components/Inline/`
**Purpose**: Lightweight UI elements embedded in chat flow
**Use Cases**: Forms, inputs, confirmations, simple interactions

### 2. Artifact Components  
**Location**: `workflows/{WorkflowName}/Components/Artifacts/`
**Purpose**: Full-featured components in dedicated panel
**Use Cases**: File downloads, code editors, complex visualizations

## Template Structure

```javascript
import React, { useState, useEffect } from 'react';

/**
 * {COMPONENT_NAME} - {COMPONENT_DESCRIPTION}
 * 
 * Props:
 * {PROP_DOCUMENTATION}
 * 
 * Actions:
 * {ACTION_DOCUMENTATION}
 */
const {COMPONENT_NAME} = ({ 
  // Required props
  {REQUIRED_PROPS},
  
  // Optional props with defaults
  {OPTIONAL_PROPS},
  
  // System props (always provided)
  onAction,        // Function to send responses back to AG2
  componentId,     // Unique identifier for this component instance
  
  // Additional props
  ...props 
}) => {
  // Component state
  {COMPONENT_STATE}
  
  // Event handlers
  {EVENT_HANDLERS}
  
  // Effect hooks
  {EFFECT_HOOKS}
  
  // Helper functions
  {HELPER_FUNCTIONS}
  
  // Render logic
  return (
    <div className="{COMPONENT_CONTAINER_CLASS}">
      {COMPONENT_JSX}
    </div>
  );
};

export default {COMPONENT_NAME};
```

## Component Contract

### Required Props Pattern
```javascript
const MyComponent = ({
  // Required business props (from AG2 agent)
  title,           // string - Component title
  data,            // object - Component data
  agentId,         // string - ID of requesting agent
  
  // System props (automatically provided)
  onAction,        // function - Response handler
  componentId,     // string - Unique component ID
  
  // Optional props with defaults
  theme = "default",
  showCloseButton = true,
  autoFocus = false
}) => {
  // Component implementation
};
```

### Action Response Pattern
```javascript
const handleUserAction = async (actionType, payload = {}) => {
  if (!onAction) {
    console.warn('onAction handler not provided');
    return;
  }
  
  try {
    await onAction({
      type: actionType,           // Action identifier
      componentId,                // Component instance ID
      agentId,                    // Agent that created component
      data: payload,              // Action-specific data
      timestamp: Date.now()       // When action occurred
    });
  } catch (error) {
    console.error(`Error handling ${actionType}:`, error);
  }
};

// Usage examples
const handleSubmit = () => {
  handleUserAction('submit', { 
    formData: formValues,
    isValid: validationPassed
  });
};

const handleCancel = () => {
  handleUserAction('cancel', { 
    reason: 'user_cancelled' 
  });
};

const handleValueChange = (newValue) => {
  handleUserAction('value_changed', { 
    value: newValue,
    field: 'target_field'
  });
};
```

## Component Categories

### 1. Input Components
Collect user data and send to backend:

```javascript
// API Key Input Component
const APIKeyInput = ({ service, agentId, onAction }) => {
  const [apiKey, setApiKey] = useState('');
  const [isVisible, setIsVisible] = useState(false);
  
  const handleSubmit = async () => {
    await onAction({
      type: 'api_key_submit',
      agentId,
      data: { 
        service,
        apiKey: apiKey.trim(),
        maskedKey: `***...${apiKey.slice(-4)}`
      }
    });
    setApiKey(''); // Clear after submit
  };
  
  return (
    <form onSubmit={handleSubmit}>
      <input 
        type={isVisible ? "text" : "password"}
        value={apiKey}
        onChange={(e) => setApiKey(e.target.value)}
        placeholder={`Enter ${service} API key`}
      />
      <button type="button" onClick={() => setIsVisible(!isVisible)}>
        {isVisible ? 'Hide' : 'Show'}
      </button>
      <button type="submit" disabled={!apiKey.trim()}>
        Submit
      </button>
    </form>
  );
};
```

### 2. Confirmation Components
Get user approval for actions:

```javascript
// Yes/No Confirmation Component  
const ConfirmationDialog = ({ 
  title, 
  message, 
  yesText = "Yes", 
  noText = "No", 
  onAction 
}) => {
  const handleResponse = (confirmed) => {
    onAction({
      type: 'confirmation_response',
      data: { 
        confirmed,
        timestamp: Date.now()
      }
    });
  };
  
  return (
    <div className="confirmation-dialog">
      <h3>{title}</h3>
      <p>{message}</p>
      <div className="actions">
        <button onClick={() => handleResponse(true)}>
          {yesText}
        </button>
        <button onClick={() => handleResponse(false)}>
          {noText}
        </button>
      </div>
    </div>
  );
};
```

### 3. Display Components
Show generated content with actions:

```javascript
// File Download Component
const FileDownloadCenter = ({ files, title, onAction }) => {
  const [downloading, setDownloading] = useState({});
  
  const handleDownload = async (file, index) => {
    setDownloading(prev => ({ ...prev, [index]: true }));
    
    try {
      await onAction({
        type: 'file_download',
        data: { 
          file,
          downloadStarted: true
        }
      });
    } finally {
      setDownloading(prev => ({ ...prev, [index]: false }));
    }
  };
  
  return (
    <div className="file-download-center">
      <h3>{title}</h3>
      {files.map((file, index) => (
        <div key={index} className="file-item">
          <span>{file.name}</span>
          <button 
            onClick={() => handleDownload(file, index)}
            disabled={downloading[index]}
          >
            {downloading[index] ? 'Downloading...' : 'Download'}
          </button>
        </div>
      ))}
    </div>
  );
};
```

### 4. Interactive Components
Complex interactions with state management:

```javascript
// Multi-Step Form Component
const MultiStepForm = ({ steps, initialData, onAction }) => {
  const [currentStep, setCurrentStep] = useState(0);
  const [formData, setFormData] = useState(initialData || {});
  const [errors, setErrors] = useState({});
  
  const handleFieldChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    // Clear field error when user starts typing
    if (errors[field]) {
      setErrors(prev => ({ ...prev, [field]: null }));
    }
  };
  
  const handleNext = () => {
    const currentStepData = steps[currentStep];
    const stepErrors = validateStep(currentStepData, formData);
    
    if (Object.keys(stepErrors).length > 0) {
      setErrors(stepErrors);
      return;
    }
    
    if (currentStep < steps.length - 1) {
      setCurrentStep(prev => prev + 1);
    } else {
      handleSubmit();
    }
  };
  
  const handleSubmit = async () => {
    await onAction({
      type: 'form_submit',
      data: {
        formData,
        completedSteps: steps.length,
        isComplete: true
      }
    });
  };
  
  return (
    <div className="multi-step-form">
      <div className="step-indicator">
        {steps.map((_, index) => (
          <div 
            key={index}
            className={`step ${index <= currentStep ? 'active' : ''}`}
          >
            {index + 1}
          </div>
        ))}
      </div>
      
      <div className="step-content">
        {renderStepFields(steps[currentStep], formData, handleFieldChange, errors)}
      </div>
      
      <div className="step-actions">
        {currentStep > 0 && (
          <button onClick={() => setCurrentStep(prev => prev - 1)}>
            Previous
          </button>
        )}
        <button onClick={handleNext}>
          {currentStep === steps.length - 1 ? 'Submit' : 'Next'}
        </button>
      </div>
    </div>
  );
};
```

## Styling Guidelines

### CSS Class Patterns
Use consistent naming for styling:

```javascript
// Container classes
className="component-container"           // Main wrapper
className="component-header"             // Header section
className="component-content"            // Main content
className="component-actions"            // Action buttons
className="component-footer"             // Footer section

// State classes
className="component-loading"            // Loading state
className="component-error"              // Error state
className="component-disabled"           // Disabled state
className="component-success"            // Success state

// Type-specific classes
className="inline-component"             // Inline component wrapper
className="artifact-component"           // Artifact component wrapper
className="form-component"               // Form-based component
className="display-component"            // Display-only component
```

### Responsive Design
```javascript
// Mobile-first responsive classes
<div className="w-full max-w-md p-4 md:max-w-lg md:p-6 lg:max-w-xl lg:p-8">
  {/* Component content */}
</div>
```

### Theme Support
```javascript
const getThemeClasses = (theme = 'default') => {
  const themes = {
    default: 'bg-white border-gray-200 text-gray-900',
    dark: 'bg-gray-800 border-gray-600 text-white',
    brand: 'bg-blue-50 border-blue-200 text-blue-900'
  };
  return themes[theme] || themes.default;
};

<div className={`component-container ${getThemeClasses(theme)}`}>
  {/* Component content */}
</div>
```

## Error Handling

### Component-Level Error Handling
```javascript
const MyComponent = ({ onAction, ...props }) => {
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  
  const handleAction = async (actionType, payload) => {
    setIsLoading(true);
    setError(null);
    
    try {
      await onAction({
        type: actionType,
        data: payload
      });
    } catch (err) {
      setError(err.message);
      console.error('Component action failed:', err);
    } finally {
      setIsLoading(false);
    }
  };
  
  if (error) {
    return (
      <div className="component-error">
        <h4>Something went wrong</h4>
        <p>{error}</p>
        <button onClick={() => setError(null)}>
          Try Again
        </button>
      </div>
    );
  }
  
  return (
    <div className={`component-container ${isLoading ? 'loading' : ''}`}>
      {/* Component content */}
    </div>
  );
};
```

### Validation Patterns
```javascript
const validateForm = (data, rules) => {
  const errors = {};
  
  Object.entries(rules).forEach(([field, rule]) => {
    const value = data[field];
    
    if (rule.required && (!value || value.toString().trim() === '')) {
      errors[field] = `${field} is required`;
      return;
    }
    
    if (rule.minLength && value.length < rule.minLength) {
      errors[field] = `${field} must be at least ${rule.minLength} characters`;
      return;
    }
    
    if (rule.pattern && !rule.pattern.test(value)) {
      errors[field] = rule.message || `${field} format is invalid`;
      return;
    }
  });
  
  return errors;
};

// Usage
const formRules = {
  email: { 
    required: true, 
    pattern: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
    message: 'Please enter a valid email address'
  },
  apiKey: { 
    required: true, 
    minLength: 10,
    pattern: /^sk-[a-zA-Z0-9]+$/,
    message: 'API key must start with sk- and contain only alphanumeric characters'
  }
};
```

## Performance Optimization

### Memoization
```javascript
import React, { memo, useMemo, useCallback } from 'react';

const OptimizedComponent = memo(({ 
  data, 
  onAction, 
  ...props 
}) => {
  // Memoize expensive calculations
  const processedData = useMemo(() => {
    return data.map(item => expensiveTransformation(item));
  }, [data]);
  
  // Memoize event handlers
  const handleAction = useCallback((type, payload) => {
    onAction({ type, data: payload });
  }, [onAction]);
  
  return (
    <div>
      {processedData.map(item => (
        <Item 
          key={item.id} 
          data={item} 
          onAction={handleAction} 
        />
      ))}
    </div>
  );
});
```

### Lazy Loading
```javascript
import { lazy, Suspense } from 'react';

// For heavy components, use lazy loading
const HeavyComponent = lazy(() => import('./HeavyComponent'));

const ParentComponent = ({ showHeavy, ...props }) => {
  return (
    <div>
      {showHeavy && (
        <Suspense fallback={<div>Loading...</div>}>
          <HeavyComponent {...props} />
        </Suspense>
      )}
    </div>
  );
};
```

## Testing Patterns

### Component Testing
```javascript
// Mock onAction for testing
const mockOnAction = jest.fn();

test('component submits form data correctly', async () => {
  render(
    <MyFormComponent 
      onAction={mockOnAction}
      initialData={{ name: '', email: '' }}
    />
  );
  
  // Fill form
  fireEvent.change(screen.getByLabelText('Name'), { 
    target: { value: 'John Doe' } 
  });
  
  // Submit form
  fireEvent.click(screen.getByText('Submit'));
  
  // Verify action was called
  expect(mockOnAction).toHaveBeenCalledWith({
    type: 'form_submit',
    data: { name: 'John Doe', email: '' }
  });
});
```

## Best Practices

1. **Single Responsibility**: Each component should have one clear purpose
2. **Prop Validation**: Use PropTypes or TypeScript for prop validation
3. **Error Boundaries**: Wrap components in error boundaries for graceful failures
4. **Accessibility**: Include ARIA labels and keyboard navigation
5. **Performance**: Use memoization for expensive operations
6. **Consistent Styling**: Follow design system patterns
7. **Clear Actions**: Make user actions obvious and accessible
8. **Loading States**: Show loading states for async operations
9. **Error Handling**: Provide clear error messages and recovery options
10. **Documentation**: Include comprehensive prop and action documentation

## 🔄 Context Adjustment Integration (NEW)

Your components can now automatically update AG2 ContextVariables through the workflow-agnostic context adjustment system.

### Enabling Context Adjustment

1. **Enable in workflow.json**: Add `"context_adjustment": true` to agents that need context updates
2. **Use proper action structure**: Components must send structured action data
3. **Optional custom handler**: Create `context_update()` function for workflow-specific logic

### Component Integration Pattern

```javascript
const ContextAwareComponent = ({ onAction, agentId, ...props }) => {
  const handleUserAction = async (actionType, payload) => {
    // Standard onAction call - automatically routes to context adjustment
    await onAction({
      type: actionType,        // Required: action identifier
      agentId: agentId,        // Required: requesting agent
      data: payload,           // Component-specific data
      timestamp: Date.now()    // Optional: when action occurred
    });
  };
  
  // Component automatically integrates with ContextVariables
  const handleSubmit = () => {
    handleUserAction('form_submit', {
      formData: formValues,
      isValid: true
    });
  };
  
  return (
    <form onSubmit={handleSubmit}>
      {/* Component UI */}
    </form>
  );
};
```

### Context Adjustment Flow

```
1. User interacts with component
   └── Component calls onAction() with structured data

2. Core system detects context_adjustment: true
   └── Routes to workflow-agnostic context adjustment bridge

3. Bridge loads workflow's context_update() function (if exists)
   └── OR applies generic context updates

4. AG2 ContextVariables updated automatically
   └── Agents can access user interaction data immediately
```

### Benefits for Component Developers

- ✅ **No backend handlers needed**: Context updates happen automatically
- ✅ **AG2 native integration**: Uses standard ContextVariables for state
- ✅ **Workflow-agnostic**: Works with any workflow configuration
- ✅ **Fallback support**: Generic updates if no custom logic provided
- ✅ **Immediate availability**: Agents can access data right after component interaction

### Example: API Key Component with Context Integration

```javascript
const AgentAPIKeyInput = ({ onAction, service, agentId, ...props }) => {
  const [apiKey, setApiKey] = useState('');
  
  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // This automatically updates ContextVariables via context adjustment
    await onAction({
      type: 'api_key_submit',
      agentId: agentId,
      data: {
        service: service,
        apiKey: apiKey.trim(),
        maskedKey: `***...${apiKey.slice(-4)}`
      }
    });
    
    setApiKey(''); // Clear sensitive data
  };
  
  const handleCancel = async () => {
    await onAction({
      type: 'cancel',
      agentId: agentId,
      data: { service: service }
    });
  };
  
  return (
    <form onSubmit={handleSubmit}>
      <input 
        type="password"
        value={apiKey}
        onChange={(e) => setApiKey(e.target.value)}
        placeholder={`Enter ${service} API key`}
        required
      />
      <div className="actions">
        <button type="submit" disabled={!apiKey.trim()}>
          Submit API Key
        </button>
        <button type="button" onClick={handleCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
};
```

**What happens behind the scenes:**
1. User submits API key → `onAction()` called
2. Core detects `context_adjustment: true` for this agent
3. Context bridge automatically stores API key in ContextVariables
4. Agents can immediately check `context_variables.get('api_key_ready')`

### Requirements for Context Adjustment

1. **workflow.json Configuration**: Agent must have `"context_adjustment": true`
2. **Structured Actions**: Use consistent action `type` and `data` structure
3. **Agent ID**: Include `agentId` for proper context routing