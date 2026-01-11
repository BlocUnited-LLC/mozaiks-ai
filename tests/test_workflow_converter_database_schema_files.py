import json
import shutil
import uuid
from pathlib import Path

import pytest

from workflows.AgentGenerator.tools.workflow_converter import create_workflow_files


@pytest.mark.asyncio
async def test_create_workflow_files_writes_schema_and_seed_files() -> None:
    workflow_name = f"TestDatabaseSchema_{uuid.uuid4().hex[:10]}"

    data = {
        "workflow_name": workflow_name,
        "orchestrator_output": {"workflow_name": workflow_name, "startup_mode": "BackendOnly"},
        "agents_output": {"agents": []},
        "handoffs_output": {"handoff_rules": []},
        "database_schema_output": {
            "DatabaseSchema": {
                "schema": {
                    "tables": [
                        {
                            "name": "users",
                            "columns": [
                                {"name": "_id", "type": "ObjectId", "constraints": ["PK"]},
                                {"name": "email", "type": "String", "constraints": ["Not Null"]},
                            ],
                            "constraints": {"unique": ["email"]},
                            "indices": ["email"],
                        }
                    ]
                },
                "seed": {
                    "users": [
                        {
                            "_id": {"$oid": "507f1f77bcf86cd799439011"},
                            "email": "demo@example.com",
                        }
                    ]
                },
            }
        },
    }

    try:
        result = await create_workflow_files(data, context_variables=None)
        assert result.get("status") == "success"

        workflow_dir = Path(result["workflow_dir"])
        schema_path = workflow_dir / "schema.json"
        seed_path = workflow_dir / "seed.json"

        assert schema_path.exists()
        assert seed_path.exists()

        schema_json = json.loads(schema_path.read_text(encoding="utf-8"))
        seed_json = json.loads(seed_path.read_text(encoding="utf-8"))

        assert schema_json["tables"][0]["name"] == "users"
        assert seed_json["users"][0]["_id"]["$oid"] == "507f1f77bcf86cd799439011"

        assert "schema.json" in (result.get("files") or [])
        assert "seed.json" in (result.get("files") or [])
    finally:
        workflow_path = Path("workflows") / workflow_name
        if workflow_path.exists():
            shutil.rmtree(workflow_path, ignore_errors=True)

