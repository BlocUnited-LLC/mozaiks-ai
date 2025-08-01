from core.workflow.file_manager import WorkflowFileManager

wfm = WorkflowFileManager()
config = wfm.load_workflow('Generator')
handoffs_config = config.get('handoffs', {})

# Handle nested structure
if 'handoffs' in handoffs_config:
    handoffs_config = handoffs_config['handoffs']

handoff_rules = handoffs_config.get('handoff_rules', [])
print(f'Total handoff rules count: {len(handoff_rules)}')
print('All handoff rules:')

for i, rule in enumerate(handoff_rules):
    source = rule.get('source_agent', 'Unknown')
    target = rule.get('target_agent', 'Unknown')
    handoff_type = rule.get('handoff_type', 'Unknown')
    condition = rule.get('condition', 'None')
    
    # Truncate long conditions
    if condition and len(str(condition)) > 60:
        condition = str(condition)[:60] + '...'
    
    print(f'  {i+1}. {source} -> {target} ({handoff_type})')
    if condition and condition != 'None':
        print(f'      Condition: {condition}')
