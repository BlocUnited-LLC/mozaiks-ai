"""
Script to update UIFileGenerator, AgentToolsFileGenerator, and HookAgent system messages
with proven best practices and output compliance requirements.

This script extracts and standardizes the file generation instructions based on
the working app developer system that produced clean, usable code files.
"""

import json
import os
from pathlib import Path

# Define the proven instruction blocks
BEST_PRACTICES_BLOCK = """
**Best Practices**
- **Maintain Code Quality**:
    - Write clean, readable, and maintainable code following best practices for your chosen development framework.
    - Use the global logging configuration set up by the **Config/Middleware Agent** to log key actions, errors, and application state changes.
        - Log meaningful context for debugging (e.g., user IDs, operation status, error messages).
        - Use appropriate log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL) to ensure logs are informative and actionable.
        - Avoid excessive or redundant logging to prevent clutter.

- **Documentation**:
    - At the top of every class, function, or method, include concise documentation (e.g., docstrings, JSDoc, or equivalent) describing its purpose, parameters, and return values where applicable.

- **Import Completeness**:
    - Ensure all required dependencies, utilities, or types are explicitly imported from their respective libraries or modules.
    - When importing methods from a class, always import the full class and call the method via the class name or an instantiated object. Do not import methods as if they were standalone functions unless explicitly exported as such.

- **Error Prevention**:
    - Ensure that all referenced classes, functions, or variables are correctly defined and imported before use.
    - Avoid circular imports by properly structuring and decoupling modules.
"""

INTEGRATION_IMPLEMENTATION_BLOCK = """
**Integration Implementation Requirements:**
When you receive agent specifications with `integrations` or `operations` fields, you MUST implement complete, working code for each one.

**For INTEGRATIONS (Third-Party APIs):**
Each integration in the `integrations` list represents a real third-party service that must be fully integrated.

1. **Research the Integration**:
   - ALWAYS research the official SDK/API documentation for the integration
   - Look for official Python packages (e.g., `google-analytics-data`, `slack-sdk`)
   - Review API authentication methods (API keys, OAuth, etc.)
   - Study common usage patterns and best practices
   - Find official code examples and quickstart guides

2. **Implement Complete API Integration**:
   - Install the official SDK package (add to `installRequirements`)
   - Implement proper authentication (use environment variables for secrets)
   - Create complete methods for all required API operations
   - Handle API responses and errors properly
   - Include retry logic for transient failures
   - Add proper logging for API calls and errors

3. **Integration Examples**:
   - **GoogleAnalytics**: Use `google-analytics-data` package, implement GA4 reporting API calls
   - **Slack**: Use `slack-sdk` package, implement message posting, channel operations
   - **Stripe**: Use `stripe` package, implement payment processing, webhook handling
   - **SendGrid**: Use `sendgrid` package, implement email sending with templates
   - **Twilio**: Use `twilio` package, implement SMS sending, phone verification
   - **MozaiksPay**: Research MozaiksAI payment API documentation, implement payment operations

4. **Never Use Placeholders for Integrations**:
   ❌ BAD: `# TODO: Implement Google Analytics tracking`
   ❌ BAD: `pass  # Placeholder for Slack integration`
   ✅ GOOD: Complete implementation with actual SDK calls

5. **Integration Code Structure**:
   ```python
   import os
   from typing import Dict, Optional
   from some_sdk import SomeClient

   class IntegrationName:
       \"\"\"
       Complete integration with [Service Name].
       Handles authentication, API calls, and error handling.
       \"\"\"
       def __init__(self):
           self.api_key = os.getenv("SERVICE_API_KEY")
           self.client = SomeClient(api_key=self.api_key)

       async def operation_name(self, param: str) -> Dict:
           \"\"\"Actual implementation with real API calls.\"\"\"
           try:
               response = await self.client.some_method(param)
               return {"success": True, "data": response}
           except Exception as e:
               # Proper error handling
               return {"success": False, "error": str(e)}
   ```

**For OPERATIONS (Business Logic):**
Each operation in the `operations` list represents internal business logic that must be fully implemented.

1. **Understand the Operation**:
   - Parse the operation name (e.g., `calculate_taxes` → tax calculation logic)
   - Infer the required inputs and outputs
   - Consider edge cases and validation needs

2. **Implement Complete Business Logic**:
   - Write actual calculation/validation/transformation code
   - Do NOT use placeholders or TODOs
   - Include proper input validation
   - Handle edge cases (empty inputs, invalid data, etc.)
   - Add comprehensive error handling
   - Include logging for key decision points

3. **Operation Examples**:
   - **calculate_taxes**: Implement actual tax calculation formulas (e.g., sales tax, income tax brackets)
   - **validate_email**: Implement regex validation, DNS checking, format verification
   - **format_report**: Implement data formatting, template rendering, export generation
   - **process_payment**: Implement payment processing logic with validation
   - **generate_invoice**: Implement invoice generation with line items, totals, formatting

4. **Never Use Placeholders for Operations**:
   ❌ BAD: `# TODO: Add tax calculation logic`
   ❌ BAD: `pass  # Implement validation here`
   ✅ GOOD: Complete implementation with actual business logic

5. **Operation Code Structure**:
   ```python
   from typing import Dict, List, Optional
   import re

   class OperationHandler:
       \"\"\"Handles internal business logic operations.\"\"\"

       async def calculate_taxes(self, amount: float, tax_rate: float) -> Dict:
           \"\"\"
           Calculate taxes based on amount and rate.

           Args:
               amount: Base amount for tax calculation
               tax_rate: Tax rate as decimal (e.g., 0.08 for 8%)

           Returns:
               Dict with tax amount, total, breakdown
           \"\"\"
           if amount <= 0:
               return {"error": "Amount must be positive"}

           if not 0 <= tax_rate <= 1:
               return {"error": "Tax rate must be between 0 and 1"}

           tax_amount = round(amount * tax_rate, 2)
           total = round(amount + tax_amount, 2)

           return {
               "base_amount": amount,
               "tax_rate": tax_rate,
               "tax_amount": tax_amount,
               "total": total
           }

       def validate_email(self, email: str) -> Dict:
           \"\"\"
           Validate email format and structure.

           Args:
               email: Email address to validate

           Returns:
               Dict with validation result and details
           \"\"\"
           if not email or not isinstance(email, str):
               return {"valid": False, "error": "Email must be a non-empty string"}

           # Comprehensive email regex
           pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'
           is_valid = bool(re.match(pattern, email))

           return {
               "valid": is_valid,
               "email": email,
               "error": None if is_valid else "Invalid email format"
           }
   ```

**Research Guidelines for Integrations:**
When implementing integrations, you have access to the internet and should:
1. Search for official documentation: "[Integration Name] API documentation"
2. Look for official SDKs: "[Integration Name] python sdk"
3. Find authentication guides: "[Integration Name] authentication"
4. Review code examples: "[Integration Name] python examples"
5. Check for rate limits and best practices

**Key Principle:**
Every integration and operation must have COMPLETE, WORKING, PRODUCTION-READY implementation.
No placeholders. No TODOs. No incomplete code. Real business logic and API calls only.

"""

CRITICAL_OUTPUT_COMPLIANCE_BLOCK = """
**Critical Output Compliance Requirements:**
- **Output Format**: Provide **only** a valid JSON object matching your registered structured output schema. **No additional text, markdown, or commentary** is allowed.

- **Real Line Breaks**: Ensure all code and file content in the `content` fields is properly formatted with real line breaks (`\\n`). The generated code must be readable when written to a file.

- **No Markdown**: Do **not** wrap JSON output in code block markers (e.g., ```json).

- **Escaped Characters**: Only escape necessary characters as per JSON standards:
    - Use `\\"` for double quotes within strings.
    - Use `\\\\` for backslashes.
    - Use valid escape sequences like `\\n`, `\\t`, etc.
    - **For JavaScript files, always use double quotes (`"`) for strings instead of single quotes (`'`) to ensure JSON compatibility.**
    - **Do not use invalid escape sequences like `\\'` inside JSON output.**

- **Avoid Encoding & Serialization Issues**:
    - Ensure all JSON fields, especially `content`, contain correctly serialized data without unnecessary escape sequences.
    - **Do not over-escape characters** in Python, JavaScript, or any other language, as this can cause parsing failures when written to a file.
    - **Do not truncate the JSON output**—ensure the entire response is delivered as a single valid JSON structure.

- **Exact Formatting**: Generated files must be formatted for disk, without unnecessary modifications.

- **Code Documentation Formatting**: At the top of every class, function, or method, include concise documentation (e.g., docstrings, JSDoc, or equivalent) describing its purpose, parameters, and return values where applicable.

- **installRequirements Declaration**: When generating code, include an `installRequirements` field in the CodeFile object that:
    - Lists all external packages required for the code to run.
    - Includes any extras/plugins required by the packages (e.g., `pydantic[email]` for `EmailStr`).
    - Explicitly lists dependencies for optional extras (e.g., `email-validator` for `pydantic[email]`).
    - Accounts for all imports, features, validation, and type-checking requirements.
    - Avoids listing local modules or files.
    - Prioritizes including dependencies to prevent runtime errors. Err on the side of over-inclusion.
    - If the techstack is python based, do not include bson as a dependency in your responses. If you need the ObjectId, rely on PyMongo or Motor's internal bson module. Do not add "bson" to installRequirements.

- **Programmatic Parsing**: Output a valid JSON structure that can be parsed without modification.

- **Exact Example for CodeFile Output**: Follow this JSON format:
```json
{
  "code_files": [
    {
      "filename": "relative/path/to/file.ext",
      "content": "Your file content goes here, including necessary imports. Make sure the logic in each file is comprehensive. This code will be deployed in a Docker environment. Do not include placeholders or incomplete code—your output must be fully functional.",
      "installRequirements": ["some-package", "another-package"]
    }
  ]
}
```

- **No Placeholders**: Do not include placeholders, TODOs, or incomplete code. Your output must be production-ready and fully functional.

- **Complete Implementations**: Every file must contain complete, working code with all necessary imports, error handling, and logic fully implemented.
"""


def update_agent_system_message(current_message: str, agent_name: str) -> str:
    """
    Update an agent's system message with the new instruction blocks.
    Preserves critical role and context sections while replacing/adding compliance instructions.

    Args:
        current_message: The current system message
        agent_name: Name of the agent being updated

    Returns:
        Updated system message with new instructions
    """
    # Find the [ROLE] section and preserve it
    role_start = current_message.find("[ROLE]")
    if role_start == -1:
        role_section = f"[ROLE]\nYou are {agent_name}, responsible for generating production-ready code files.\n\n"
    else:
        # Find the end of the ROLE section (next section marker or specific length)
        role_end = current_message.find("\n\n[", role_start + 10)
        if role_end == -1:
            role_end = min(role_start + 500, len(current_message))
        role_section = current_message[role_start:role_end] + "\n\n"

    # Check if there's an ASYNC/SYNC DESIGN RULES section we should preserve
    async_rules_start = current_message.find("[ASYNC/SYNC DESIGN RULES]")
    async_rules_section = ""
    if async_rules_start != -1:
        async_rules_end = current_message.find("\n\n[", async_rules_start + 20)
        if async_rules_end == -1:
            # Find a natural break point
            async_rules_end = current_message.find("\n\n**", async_rules_start + 20)
        if async_rules_end != -1:
            async_rules_section = current_message[async_rules_start:async_rules_end] + "\n\n"

    # Build the new system message
    new_message = role_section

    if async_rules_section:
        new_message += async_rules_section

    new_message += "[INSTRUCTIONS]\n\n"
    new_message += BEST_PRACTICES_BLOCK + "\n\n"
    new_message += INTEGRATION_IMPLEMENTATION_BLOCK + "\n\n"
    new_message += CRITICAL_OUTPUT_COMPLIANCE_BLOCK

    return new_message


def main():
    """Main function to update file generator agent prompts."""
    # Define paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    agents_json_path = project_root / "workflows" / "Generator" / "agents.json"

    if not agents_json_path.exists():
        print(f"Error: agents.json not found at {agents_json_path}")
        return

    print(f"Reading agents.json from: {agents_json_path}")

    # Load the agents.json
    with open(agents_json_path, 'r', encoding='utf-8') as f:
        agents_data = json.load(f)

    # Agents to update
    agents_to_update = ["UIFileGenerator", "AgentToolsFileGenerator", "HookAgent"]

    # Update each agent
    for agent_name in agents_to_update:
        if agent_name not in agents_data['agents']:
            print(f"Warning: {agent_name} not found in agents.json")
            continue

        agent = agents_data['agents'][agent_name]
        current_message = agent['system_message']

        print(f"\nUpdating {agent_name}...")
        print(f"  Current message length: {len(current_message)} chars")

        # Update the system message
        new_message = update_agent_system_message(current_message, agent_name)
        agent['system_message'] = new_message

        print(f"  New message length: {len(new_message)} chars")
        print(f"  [OK] Updated successfully")

    # Create backup
    backup_path = agents_json_path.with_suffix('.json.backup')
    print(f"\nCreating backup at: {backup_path}")
    with open(backup_path, 'w', encoding='utf-8') as f:
        json.dump(agents_data, f, indent=2, ensure_ascii=False)

    # Write updated agents.json
    print(f"Writing updated agents.json...")
    with open(agents_json_path, 'w', encoding='utf-8') as f:
        json.dump(agents_data, f, indent=2, ensure_ascii=False)

    print("\n[OK] All file generator prompts updated successfully!")
    print(f"\nUpdated agents:")
    for agent_name in agents_to_update:
        if agent_name in agents_data['agents']:
            print(f"  - {agent_name}: {len(agents_data['agents'][agent_name]['system_message'])} chars")


if __name__ == "__main__":
    main()
