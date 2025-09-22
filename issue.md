So i am trying to register ag2 context variaribles via a declariative manner via context_variables.json unfornatley i dont believe these varaibles are getting registered per ag2 logic as the app is not functioning the way i want it to. for 1 during my most recent test the InterviewAgent presented the output "NEXT" exactly as it is setup in the context_variables.json and 2 the prompt itself says to reference any context varaibles and the agent is not referencing nay context varaibles so i dont think our context vaiable logic is working properly.

the goal was to have the ability to define context varaibles through .json thats hot swapable across any type of use cases. from how i see it there are 2 ways to get context either thats 1 from a db or derived by the conversation and set by an agent of sorts.

the associated sourcecode logic is found via:

.venv\Lib\site-packages\autogen\agentchat\group\context_variables.py
.venv\Lib\site-packages\autogen\agentchat\group\context_expression.py
.venv\Lib\site-packages\autogen\agentchat\group\context_condition.py

Currently i have the folllowing logic that includes context varialbes in them:

workflows\Generator\context_variables.json
core\workflow\context_variables.py
core\workflow\derived_context.py
core\workflow\orchestration_patterns.py

ag2 allows for these declariative types of contexT_variables. per their documentation as described below:

Context Variables
Context Variables provide shared memory for your agents, allowing them to maintain state across a conversation and make decisions based on that shared information. If tools are the specialized capabilities agents can use, context variables are their collective knowledge base.

The ContextVariables Class#
Context variables in AG2 are implemented through the ContextVariables class, which provides a dictionary-like interface to store and retrieve values:

from autogen.agentchat.group import ContextVariables

Create context variables
context = ContextVariables(data={
"user_name": "Alex",
"issue_count": 0,
"previous_issues": []
})
Core Functionality#
Creating and Initializing Context Variables#
You can create context variables when setting up your group chat pattern:

from autogen.agentchat.group import ContextVariables
from autogen.agentchat.group.patterns import AutoPattern

Initialize context variables with initial data
context = ContextVariables(data={
"user_name": "Alex",
"issue_count": 0,
"previous_issues": []
})

Create pattern with the context variables
pattern = AutoPattern(
initial_agent=triage_agent,
agents=[triage_agent, tech_agent, general_agent],
user_agent=user,
context_variables=context, # Pass context variables to the pattern
group_manager_args={"llm_config": llm_config}
)
Reading and Writing Context Values#
The ContextVariables class provides several methods for reading and writing values:

Reading values
user_name = context.get("user_name") # Returns "Alex"
non_existent = context.get("non_existent", "default") # Returns "default"

Writing values
context.set("issue_count", 1) # Sets issue_count to 1
context.update({"last_login": "2023-05-01", "premium": True}) # Update multiple values
Dictionary-like Interface#
The ContextVariables class implements a dictionary-like interface, allowing you to use a familiar syntax:

Dictionary-like operations
user_name = context["user_name"] # Get a value
context["issue_count"] = 2 # Set a value
del context["temporary_value"] # Delete a value
if "premium" in context: # Check if a key exists
print("Premium user")

Iterate over keys and values
for key, value in context:
print(f"{key}: {value}")
Persistence Across Agent Transitions#
One of the most powerful features of context variables is their persistence across agent transitions. When control passes from one agent to another, the context variables go with it, maintaining the shared state.

In the below example, the route_to_tech_support function updates the context variables with the current issue and passes the control to the tech support agent who can then access the updated context variables to make informed decisions.

def route_to_tech_support(issue: str, context_variables: ContextVariables) -> ReplyResult:
"""Route an issue to technical support."""
# Update the context with the current issue
context_variables["current_issue"] = issue
context_variables["issue_count"] += 1
context_variables["previous_issues"].append(issue)

# Return control to the tech agent with the updated context
return ReplyResult(
    message="Routing to technical support...",
    target=AgentTarget(tech_agent),
    context_variables=context_variables  # Update the shared context
)

How Agents Access Context Variables#
Context Variables are NOT Automatically Visible to LLMs

Context variables are not automatically included in the prompts sent to LLMs. Unlike conversation history, which is always visible, context variables remain in AG2's memory layer and must be explicitly accessed through specific mechanisms provided by the framework.

Creating Context Summary Tools#
For complex contexts, create dedicated tools that summarize the current state:

def get_session_summary(context_variables: ContextVariables) -> str:
"""Get a summary of the current support session."""
summary = f"""
Session Summary:
- User: {context_variables.get('user_name', 'Unknown')}
- Session Duration: {calculate_duration(context_variables.get('session_start'))}
- Issues Reported: {context_variables.get('issue_count', 0)}
- Current Status: {context_variables.get('status', 'Active')}
- Last Action: {context_variables.get('last_action', 'None')}
"""
return summary

Context Variables in Handoffs#
Agent handoffs provide a sophisticated mechanism for using context variables to control conversation flow. Unlike tools and system messages where agents actively access context, handoffs use context to automatically determine routing between agents.

Context-Based Handoffs (OnContextCondition)#
The most efficient way to route agents based on context is through OnContextCondition. These conditions evaluate context variables directly without using the LLM:

from autogen.agentchat.group import OnContextCondition, ExpressionContextCondition, ContextExpression
from autogen.agentchat.group import StringContextCondition, AgentTarget

Simple context check - triggers when 'logged_in' is truthy
agent.handoffs.add_context_condition(
OnContextCondition(
target=AgentTarget(order_mgmt_agent),
condition=StringContextCondition(variable_name="logged_in")
)
)

Complex expression - evaluates boolean expressions on context
agent.handoffs.add_context_condition(
OnContextCondition(
target=AgentTarget(advanced_support),
condition=ExpressionContextCondition(
ContextExpression("${issue_count} >= 3 and ${is_premium} == True")
)
)
)
These conditions are evaluated automatically before each agent response, without any LLM involvement.

LLM-Based Handoffs with Context (OnCondition)#
For more nuanced decisions that require understanding message content, use OnCondition with context-aware prompts:

from autogen.agentchat.group import OnCondition, ContextStrLLMCondition, ContextStr
from autogen.agentchat.group import StringAvailableCondition

The ContextStr template substitutes context variables into the prompt
agent.handoffs.add_llm_condition(
OnCondition(
target=AgentTarget(tech_support),
condition=ContextStrLLMCondition(
ContextStr("Transfer to tech support if the user mentions technical issues. "
"Current user: {user_name}, Issue count: {issue_count}")
)
)
)
AG2 dynamically substitutes context variables into these prompts before each agent response, so the LLM sees actual values (e.g., "Current user: John, Issue count: 3") without the context being part of the conversation history.

Conditional Availability#
Both types of handoffs can be conditionally available based on context:

This handoff is only available when not logged in
OnCondition(
target=AgentTarget(auth_agent),
condition=StringLLMCondition("Transfer to authentication if user needs to log in"),
available=StringAvailableCondition(context_variable="requires_login")
)
How It All Works Together#
The context-aware handoff mechanism provides a powerful way to create dynamic agent workflows:

Context conditions (OnContextCondition) evaluate first, enabling instant routing without LLM calls
LLM conditions (OnCondition) see prompts with current context values substituted
Availability filters control which handoff options are active based on application state
All context remains separate from the conversation history, maintaining clean prompts
This design allows you to build sophisticated routing logic that adapts to your application's state while keeping LLM prompts focused and token-efficient.

===========