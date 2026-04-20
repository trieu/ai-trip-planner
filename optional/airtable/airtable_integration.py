"""
Airtable Integration for AI Trip Planner (moved to optional/airtable)
Captures traces for manual labeling and evaluation
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from pyairtable import Api
from pyairtable.formulas import match
import hashlib

class AirtableTraceLogger:
    """Handles logging traces to Airtable for manual labeling"""
    
    def __init__(self):
        self.api_key = os.getenv("AIRTABLE_API_KEY")
        self.base_id = os.getenv("AIRTABLE_BASE_ID")
        self.table_name = os.getenv("AIRTABLE_TABLE_NAME", "trip_planner_traces")
        
        if not self.api_key or not self.base_id:
            print("⚠️ Airtable credentials not configured. Trace logging to Airtable disabled.")
            print("📝 Set AIRTABLE_API_KEY and AIRTABLE_BASE_ID in your .env file")
            self.enabled = False
            return
            
        try:
            self.api = Api(self.api_key)
            self.table = self.api.table(self.base_id, self.table_name)
            self.enabled = True
            print("✅ Airtable trace logger initialized")
            print(f"📊 Base ID: {self.base_id[:10]}...")
            print(f"📋 Table: {self.table_name}")
            self._ensure_table_schema()
        except Exception as e:
            print(f"❌ Failed to initialize Airtable: {str(e)}")
            self.enabled = False
    
    def _ensure_table_schema(self):
        """Ensure the Airtable has the required fields"""
        required_fields = [
            "trace_id",
            "timestamp",
            "destination",
            "duration",
            "budget",
            "interests",
            "travel_style",
            "request_payload",
            "response_result",
            "tool_calls",
            "research_data",
            "budget_data",
            "local_data",
            "final_journey_plan",
            "latency_ms",
            "success",
            "error_message",
            "human_label_quality",  # For manual labeling
            "human_label_accuracy",  # For manual labeling
            "human_label_notes",     # For manual labeling
            "labeled_by",           # For tracking who labeled
            "labeled_at",           # When it was labeled
        ]
        # Note: Airtable doesn't have a direct API to check/create fields
        # This is just documentation of expected schema
        print(f"📝 Expected Airtable fields: {', '.join(required_fields[:5])}...")

    def _strip_unknown_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove optional labeling fields that may not exist in the Airtable schema."""
        cleaned = dict(data)
        for k in ("human_label_notes", "labeled_by", "labeled_at"):
            cleaned.pop(k, None)
        return cleaned

    def _should_retry_without_labels(self, err: Exception) -> bool:
        msg = str(err)
        return (
            "UNKNOWN_FIELD_NAME" in msg
            or "Unknown field name" in msg
            or "422" in msg
        )

    def _safe_create(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Create a record; on 422 unknown field error, retry without label fields."""
        try:
            return self.table.create(record)
        except Exception as e:
            if self._should_retry_without_labels(e):
                print("ℹ️ Airtable create failed due to unknown field; retrying without label fields.")
                cleaned = self._strip_unknown_fields(record)
                return self.table.create(cleaned)
            raise

    def _safe_update(self, record_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        """Update a record; on 422 unknown field error, retry without label fields."""
        try:
            return self.table.update(record_id, fields)
        except Exception as e:
            if self._should_retry_without_labels(e):
                print("ℹ️ Airtable update failed due to unknown field; retrying without label fields.")
                cleaned = self._strip_unknown_fields(fields)
                return self.table.update(record_id, cleaned)
            raise
    
    def log_trace(self, 
                  request: Dict[str, Any],
                  response: Dict[str, Any],
                  state_data: Dict[str, Any],
                  latency_ms: float,
                  success: bool = True,
                  error_message: str = None) -> Optional[str]:
        """Log a trace to Airtable for manual labeling"""
        
        if not self.enabled:
            return None
            
        try:
            # Generate a unique trace ID
            trace_id = hashlib.md5(
                f"{datetime.utcnow().isoformat()}{json.dumps(request)}".encode()
            ).hexdigest()
            
            # Extract tool calls information
            tool_calls = state_data.get("tool_calls", [])
            tool_calls_summary = self._summarize_tool_calls(tool_calls)
            
            # Prepare record for Airtable
            record = {
                "trace_id": trace_id,
                "timestamp": datetime.utcnow().isoformat(),
                "destination": request.get("destination", ""),
                "duration": request.get("duration", ""),
                "budget": request.get("budget", ""),
                "interests": request.get("interests", ""),
                "travel_style": request.get("travel_style", ""),
                "request_payload": json.dumps(request),
                "response_result": response.get("result", "")[:50000],  # Airtable has field limits
                "tool_calls": json.dumps(tool_calls_summary),
                "research_data": str(state_data.get("research_data", ""))[:10000],
                "budget_data": str(state_data.get("budget_data", ""))[:10000],
                "local_data": str(state_data.get("local_data", ""))[:10000],
                "final_journey_plan": str(state_data.get("final_result", ""))[:50000],
                "latency_ms": latency_ms,
                "success": success,
                "error_message": error_message or "",
                # Leave labeling fields empty for manual annotation
                # Don't include select fields with empty values - they'll be added when labeled
                "human_label_notes": "",
                "labeled_by": "",
                "labeled_at": ""
            }
            
            # Create record in Airtable
            created_record = self._safe_create(record)
            record_id = created_record["id"]
            
            print(f"📤 Trace logged to Airtable: {trace_id} (Record: {record_id})")
            return record_id
            
        except Exception as e:
            print(f"❌ Failed to log trace to Airtable: {str(e)}")
            return None
    
    def _summarize_tool_calls(self, tool_calls: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Summarize tool calls for storage"""
        summary = {
            "total_calls": len(tool_calls),
            "by_agent": {},
            "by_tool": {},
            "details": []
        }
        
        for call in tool_calls:
            agent = call.get("agent", "unknown")
            tool = call.get("tool", "unknown")
            
            # Count by agent
            summary["by_agent"][agent] = summary["by_agent"].get(agent, 0) + 1
            
            # Count by tool
            summary["by_tool"][tool] = summary["by_tool"].get(tool, 0) + 1
            
            # Add simplified details
            summary["details"].append({
                "agent": agent,
                "tool": tool,
                "args": call.get("args", {})
            })
        
        return summary
    
    def get_unlabeled_traces(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve traces that haven't been labeled yet"""
        if not self.enabled:
            return []
            
        try:
            # Get records where human_label_quality is empty
            formula = match({"human_label_quality": ""})
            records = self.table.all(formula=formula, max_records=limit)
            
            traces = []
            for record in records:
                trace = {
                    "record_id": record["id"],
                    "trace_id": record["fields"].get("trace_id"),
                    "timestamp": record["fields"].get("timestamp"),
                    "destination": record["fields"].get("destination"),
                    "request": json.loads(record["fields"].get("request_payload", "{}")),
                    "response": record["fields"].get("response_result"),
                    "tool_calls": json.loads(record["fields"].get("tool_calls", "{}")),
                }
                traces.append(trace)
            
            print(f"📥 Retrieved {len(traces)} unlabeled traces from Airtable")
            return traces
            
        except Exception as e:
            print(f"❌ Failed to retrieve unlabeled traces: {str(e)}")
            return []
    
    def get_labeled_traces(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Retrieve traces that have been labeled for evaluation"""
        if not self.enabled:
            return []
            
        try:
            # Get records where human_label_quality is not empty
            records = self.table.all(max_records=limit)
            labeled_records = [r for r in records if r["fields"].get("human_label_quality")]
            
            traces = []
            for record in labeled_records:
                fields = record["fields"]
                trace = {
                    "record_id": record["id"],
                    "trace_id": fields.get("trace_id"),
                    "timestamp": fields.get("timestamp"),
                    "request": json.loads(fields.get("request_payload", "{}")),
                    "response": fields.get("response_result"),
                    "tool_calls": json.loads(fields.get("tool_calls", "{}")),
                    "research_data": fields.get("research_data"),
                    "budget_data": fields.get("budget_data"),
                    "local_data": fields.get("local_data"),
                    "final_journey_plan": fields.get("final_journey_plan"),
                    "labels": {
                        "quality": fields.get("human_label_quality"),
                        "accuracy": fields.get("human_label_accuracy"),
                        "notes": fields.get("human_label_notes"),
                        "labeled_by": fields.get("labeled_by"),
                        "labeled_at": fields.get("labeled_at")
                    }
                }
                traces.append(trace)
            
            print(f"📥 Retrieved {len(traces)} labeled traces from Airtable")
            return traces
            
        except Exception as e:
            print(f"❌ Failed to retrieve labeled traces: {str(e)}")
            return []
    
    def update_labels(self, record_id: str, labels: Dict[str, Any]) -> bool:
        """Update labels for a specific trace"""
        if not self.enabled:
            return False
            
        try:
            # Add timestamp for when it was labeled
            labels["labeled_at"] = datetime.utcnow().isoformat()
            
            # Update the record
            self.table.update(record_id, labels)
            print(f"✅ Updated labels for record {record_id}")
            return True
            
        except Exception as e:
            print(f"❌ Failed to update labels: {str(e)}")
            return False
    
    def get_trace_by_id(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific trace by its trace_id"""
        if not self.enabled:
            return None
            
        try:
            formula = match({"trace_id": trace_id})
            records = self.table.all(formula=formula, max_records=1)
            
            if records:
                record = records[0]
                return {
                    "record_id": record["id"],
                    "fields": record["fields"]
                }
            return None
            
        except Exception as e:
            print(f"❌ Failed to retrieve trace: {str(e)}")
            return None
    
    def log_request(self, request_data: Dict[str, Any]) -> Optional[str]:
        """Log an incoming request to Airtable"""
        if not self.enabled:
            return None
            
        try:
            # Generate a unique trace ID
            trace_id = hashlib.md5(
                f"{datetime.utcnow().isoformat()}{json.dumps(request_data)}".encode()
            ).hexdigest()
            
            # Prepare basic record for the request
            record = {
                "trace_id": trace_id,
                "timestamp": datetime.utcnow().isoformat(),
                "destination": request_data.get("destination", ""),
                "duration": request_data.get("duration", ""),
                "budget": request_data.get("budget", ""),
                "interests": request_data.get("interests", ""),
                "travel_style": request_data.get("travel_style", ""),
                "request_payload": json.dumps(request_data),
                "success": False,  # Will be updated when response is ready
                "human_label_notes": "",
                "labeled_by": "",
                "labeled_at": ""
            }
            
            # Create record in Airtable
            created_record = self._safe_create(record)
            record_id = created_record["id"]
            
            print(f"📤 Request logged to Airtable: {trace_id} (Record: {record_id})")
            return trace_id
            
        except Exception as e:
            print(f"❌ Failed to log request to Airtable: {str(e)}")
            return None
    
    def log_error(self, request_data: Dict[str, Any], error_message: str) -> None:
        """Log an error that occurred during processing"""
        if not self.enabled:
            return
            
        try:
            # Generate the same trace ID as the request
            trace_id = hashlib.md5(
                f"{datetime.utcnow().isoformat()}{json.dumps(request_data)}".encode()
            ).hexdigest()
            
            # Try to find and update existing record
            existing_trace = self.get_trace_by_id(trace_id)
            
            if existing_trace:
                # Update existing record with error
                self._safe_update(existing_trace["record_id"], {
                    "success": False,
                    "error_message": error_message
                })
                print(f"📤 Error logged to existing trace: {trace_id}")
            else:
                # Create new error record
                record = {
                    "trace_id": trace_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "destination": request_data.get("destination", ""),
                    "duration": request_data.get("duration", ""),
                    "budget": request_data.get("budget", ""),
                    "interests": request_data.get("interests", ""),
                    "travel_style": request_data.get("travel_style", ""),
                    "request_payload": json.dumps(request_data),
                    "success": False,
                    "error_message": error_message,
                    "human_label_notes": "",
                    "labeled_by": "",
                    "labeled_at": ""
                }
                
                created_record = self._safe_create(record)
                print(f"📤 Error logged to new Airtable record: {trace_id}")
                
        except Exception as e:
            print(f"❌ Failed to log error to Airtable: {str(e)}")
    
    def log_response(self, request_data: Dict[str, Any], response_result: str, tool_calls: List[Dict[str, Any]]) -> None:
        """Log a successful response to Airtable"""
        if not self.enabled:
            return
            
        try:
            # Generate the same trace ID as the request
            trace_id = hashlib.md5(
                f"{datetime.utcnow().isoformat()}{json.dumps(request_data)}".encode()
            ).hexdigest()
            
            # Summarize tool calls
            tool_calls_summary = self._summarize_tool_calls(tool_calls)
            
            # Try to find and update existing record
            existing_trace = self.get_trace_by_id(trace_id)
            
            if existing_trace:
                # Update existing record with response
                self._safe_update(existing_trace["record_id"], {
                    "response_result": response_result[:50000],  # Airtable has field limits
                    "tool_calls": json.dumps(tool_calls_summary),
                    "success": True
                })
                print(f"📤 Response logged to existing trace: {trace_id}")
            else:
                # Create new record with response
                record = {
                    "trace_id": trace_id,
                    "timestamp": datetime.utcnow().isoformat(),
                    "destination": request_data.get("destination", ""),
                    "duration": request_data.get("duration", ""),
                    "budget": request_data.get("budget", ""),
                    "interests": request_data.get("interests", ""),
                    "travel_style": request_data.get("travel_style", ""),
                    "request_payload": json.dumps(request_data),
                    "response_result": response_result[:50000],
                    "tool_calls": json.dumps(tool_calls_summary),
                    "success": True,
                    "human_label_notes": "",
                    "labeled_by": "",
                    "labeled_at": ""
                }
                
                created_record = self._safe_create(record)
                print(f"📤 Response logged to new Airtable record: {trace_id}")
                
        except Exception as e:
            print(f"❌ Failed to log response to Airtable: {str(e)}")

# Create a singleton instance
airtable_logger = AirtableTraceLogger() 
