import core.workflow.context_variables as cv
print('context_variables imported OK')
from pathlib import Path
print('agents.json snippet:')
print(Path('workflows/Generator/agents.json').read_text()[:220])
