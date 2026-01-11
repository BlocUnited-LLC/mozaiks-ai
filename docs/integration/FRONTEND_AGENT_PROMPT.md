# Frontend Agent Prompt — MozaiksAI Integration

**Role**: You build UI pages and components that integrate MozaiksAI.

**Your Job**: Provide page context for Ask Mozaiks. Trigger workflows when needed. That's it.

---

## 1. Two Modes — Different Purposes

| Mode | What It Is | UI Surface | Context Needed |
|------|-----------|------------|----------------|
| **Ask Mozaiks** | General Q&A assistant | Widget/bubble on any page | Page context (where user is, what they're viewing) |
| **Workflow Mode** | Specific task workflow | Full-screen overlay | Just workflow name (workflow defines its own context) |

```
┌─────────────────────────────────────────────────────────────────┐
│  ASK MOZAIKS (Widget)                                           │
│  ─────────────────────────────────────────────────────────────  │
│  • User stays on current page                                   │
│  • Agent needs to know page context to help                     │
│  • "I see you're on the Investor tab with $50k balance..."      │
│  • Modular prompt handles any question using context vars       │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  WORKFLOW MODE (Full Overlay)                                   │
│  ─────────────────────────────────────────────────────────────  │
│  • Full-screen takeover                                         │
│  • User is "in the workflow", not on a page                     │
│  • Workflow already knows what context it needs                 │
│  • Context defined during AgentGenerator, not by frontend       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Ask Mozaiks — Page Context

Every page should provide context so Ask Mozaiks can help intelligently.

### What to Provide

```javascript
// Page context = what the user is looking at right now
const pageContext = {
  // REQUIRED: Where are they?
  page: 'discovery',
  section: 'investors',
  
  // RELEVANT: What data is visible to them?
  accountBalance: user.balance,
  existingHoldings: user.holdings,
  selectedInvestor: selectedInvestor?.name,
  
  // HELPFUL: What are they trying to do?
  action: 'browsing'  // or 'comparing', 'researching', etc.
};

// Send to Ask Mozaiks when widget opens
window.mozaiksChat.open({
  mode: 'ask',
  context: pageContext
});
```

### Context by Page Type

**Dashboard**
```javascript
context: {
  page: 'dashboard',
  section: 'overview',
  metrics: {
    totalBalance: user.balance,
    portfolioValue: portfolio.total,
    recentActivity: activities.slice(0, 5)
  },
  dateRange: selectedDateRange
}
```

**Discovery / Browse Page**
```javascript
context: {
  page: 'discovery',
  section: 'investors',        // or 'opportunities', 'startups'
  filters: activeFilters,
  selectedItem: selectedInvestor?.id,
  userBalance: user.availableFunds,
  userHoldings: user.holdings.map(h => h.name)
}
```

**Detail Page**
```javascript
context: {
  page: 'investor_detail',
  investorId: investor.id,
  investorName: investor.name,
  investorMetrics: {
    aum: investor.aum,
    returns: investor.historicalReturns
  },
  userCanInvest: user.balance >= investor.minimumInvestment
}
```

**Settings / Profile**
```javascript
context: {
  page: 'settings',
  section: 'account',          // or 'security', 'notifications'
  currentValues: {
    emailVerified: user.emailVerified,
    twoFactorEnabled: user.twoFactor
  }
}
```

### How Ask Mozaiks Uses This

The Ask Mozaiks agent receives these as `ui_` prefixed variables:
- `ui_page` → `"discovery"`
- `ui_section` → `"investors"`
- `ui_accountBalance` → `50000`
- `ui_existingHoldings` → `["Fund A", "Fund B"]`

Agent can then respond contextually:
> *"I see you're browsing investors in Discovery. You have $50k available and already hold Fund A and Fund B. Looking for something specific?"*

---

## 3. Workflow Mode — Minimal Context

Workflows are self-contained. They define their own context needs during generation.

### When to Trigger

```javascript
// User explicitly starts a workflow (button, menu, etc.)
window.mozaiksChat.open({
  mode: 'workflow',
  workflow_name: 'InvestmentWizard'
});

// Resume existing workflow
window.mozaiksChat.open({
  mode: 'workflow',
  workflow_name: 'InvestmentWizard',
  chat_id: 'existing_chat_id'
});
```

### What NOT to Do

```javascript
// ❌ DON'T pass page context to workflows
window.mozaiksChat.open({
  mode: 'workflow',
  workflow_name: 'InvestmentWizard',
  context: {                    // ← Not needed
    page: 'dashboard',          // Workflow doesn't care
    balance: user.balance       // Workflow fetches this itself
  }
});

// ✅ DO just specify the workflow
window.mozaiksChat.open({
  mode: 'workflow',
  workflow_name: 'InvestmentWizard'
});
```

**Why?** Workflows already define their context needs in `context_variables.json` during AgentGenerator. The workflow knows what data it needs and how to get it (via data_reference, computed, etc.).

---

## 4. UI Implementation

### Ask Mozaiks Widget (Every Page)

```jsx
function AskMozaiksWidget({ pageContext }) {
  return (
    <button 
      onClick={() => window.mozaiksChat?.open({
        mode: 'ask',
        context: pageContext
      })}
      className="fixed bottom-4 right-4 rounded-full bg-blue-600 p-4 shadow-lg"
      aria-label="Ask Mozaiks"
    >
      <ChatIcon />
    </button>
  );
}
```

### Page with Context Provider

```jsx
function DiscoveryPage() {
  const { user } = useAuth();
  const [section, setSection] = useState('investors');
  const [selectedItem, setSelectedItem] = useState(null);
  const [filters, setFilters] = useState({});

  // Build page context for Ask Mozaiks
  const pageContext = {
    page: 'discovery',
    section,
    filters,
    selectedItemId: selectedItem?.id,
    selectedItemName: selectedItem?.name,
    userBalance: user.availableFunds,
    userHoldings: user.holdings.map(h => h.name)
  };

  return (
    <div>
      <Tabs value={section} onChange={setSection}>
        <Tab value="investors">Investors</Tab>
        <Tab value="opportunities">Opportunities</Tab>
      </Tabs>
      
      <FilterBar filters={filters} onChange={setFilters} />
      <ItemList onSelect={setSelectedItem} />
      
      {/* Ask Mozaiks knows about current page state */}
      <AskMozaiksWidget pageContext={pageContext} />
    </div>
  );
}
```

### Workflow Trigger (Specific Action)

```jsx
function InvestmentCTA() {
  return (
    <button onClick={() => window.mozaiksChat?.open({
      mode: 'workflow',
      workflow_name: 'InvestmentWizard'
    })}>
      Start Investment Wizard
    </button>
  );
}
```

---

## 5. Context Rules

### For Ask Mozaiks (Page Context)

| Include | Don't Include |
|---------|---------------|
| Current page/section | Auth tokens |
| Visible data summaries | Full database objects |
| User's relevant state (balance, holdings) | Internal IDs unless needed |
| Active filters/selections | Sensitive PII |
| What action they might be taking | Implementation details |

### For Workflow Mode

| Include | Don't Include |
|---------|---------------|
| `workflow_name` | Page context |
| `chat_id` (if resuming) | User data (workflow fetches it) |
| | Anything else |

---

## 6. Ask Mozaiks Full-Screen (Temporary Approach)

When Ask Mozaiks is opened full-screen (not from a specific page), use the **last known page context** as a fallback:

```jsx
// Store last page context in a ref or global state
const lastPageContextRef = useRef(null);

// Update it whenever user navigates
useEffect(() => {
  lastPageContextRef.current = buildPageContext();
}, [location.pathname, /* other relevant deps */]);

// When opening Ask Mozaiks full-screen
window.mozaiksChat.open({
  mode: 'ask',
  context: lastPageContextRef.current || { page: 'unknown', section: 'general' }
});
```

> ⚠️ **TODO: This is a temporary solution.** Full-screen Ask Mozaiks should eventually have comprehensive user context (full profile, history, preferences, holdings summary) via RAG integration rather than just "last page visited". This requires backend work to aggregate user data into a queryable context. For now, falling back to last page context is acceptable but will feel limited when users open Ask Mozaiks from the home screen or after a fresh login.

---

## 7. Keyboard Shortcut

```jsx
useEffect(() => {
  const handleKeyDown = (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      // Opens Ask Mozaiks with current page context
      window.mozaiksChat?.open({
        mode: 'ask',
        context: getCurrentPageContext()  // Your context builder
      });
    }
  };
  window.addEventListener('keydown', handleKeyDown);
  return () => window.removeEventListener('keydown', handleKeyDown);
}, []);
```

---

## 8. Checklist

### Every Page (Ask Mozaiks)
- [ ] Page provides context object with `page`, `section`
- [ ] Relevant user state included (balance, holdings, etc.)
- [ ] Visible data summarized (not full objects)
- [ ] AskMozaiksWidget rendered with context

### Workflow Triggers
- [ ] Button/action triggers `mode: 'workflow'`
- [ ] `workflow_name` specified
- [ ] NO page context passed (workflow handles its own)

---

## 9. What You Don't Do

- Don't pass page context to workflows (they're self-contained)
- Don't implement the Ask Mozaiks agent logic (that's runtime/backend)
- Don't handle full-screen Ask mode context (future feature)
- Don't validate users (session broker handles auth)

**Your job:**
- Ask Mode → provide rich page context
- Workflow Mode → just trigger with workflow name
