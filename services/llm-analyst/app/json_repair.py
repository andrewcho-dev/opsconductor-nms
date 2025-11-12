import json
import logging

logger = logging.getLogger(__name__)


def repair_truncated_json(broken_json: str) -> str:
    """Attempt to repair truncated JSON from LLM hitting max_tokens."""
    json_str = broken_json.strip()
    
    depth_brace = 0
    depth_bracket = 0
    in_string = False
    escape_next = False
    
    for char in json_str:
        if escape_next:
            escape_next = False
            continue
            
        if char == '\\':
            escape_next = True
            continue
            
        if char == '"' and not in_string:
            in_string = True
        elif char == '"' and in_string:
            in_string = False
        elif not in_string:
            if char == '{':
                depth_brace += 1
            elif char == '}':
                depth_brace -= 1
            elif char == '[':
                depth_bracket += 1
            elif char == ']':
                depth_bracket -= 1
    
    if in_string:
        logger.warning("Closing unterminated string")
        json_str += '"'
    
    if depth_bracket > 0:
        logger.warning(f"Closing {depth_bracket} unclosed brackets")
        json_str += ']' * depth_bracket
        
    if depth_brace > 0:
        logger.warning(f"Closing {depth_brace} unclosed braces")
        json_str += '}' * depth_brace
    
    return json_str
