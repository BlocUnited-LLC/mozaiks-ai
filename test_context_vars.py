from core.workflow.file_manager import WorkflowFileManager

wfm = WorkflowFileManager()
config = wfm.load_workflow('Generator')
ctx_vars = config.get('context_variables', {})

print('Context variables keys:', list(ctx_vars.keys()))

# Handle nested structure
if 'context_variables' in ctx_vars:
    ctx_vars = ctx_vars['context_variables']

variables = ctx_vars.get('variables', [])
print('Context variables found:', len(variables))
if variables:
    print('Variables:')
    for i, var in enumerate(variables):
        print(f'  {i+1}. {var.get("name", "unknown")}: {var.get("description", "no description")}')
else:
    print('No variables found')
