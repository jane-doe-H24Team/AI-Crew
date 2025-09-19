import importlib
import inspect
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class ToolManager:
    def __init__(self):
        self.tools = {}
        self._load_tools()

    def _load_tools(self):
        tools_dir = Path(__file__).parent
        logger.debug(f"Scanning for tools in: {tools_dir}")
        for tool_file in tools_dir.glob("*.py"):
            if tool_file.name.startswith("__"):
                continue
            
            module_name = f"avatar_manager.tools.{tool_file.stem}"
            logger.debug(f"Attempting to load module: {module_name}")
            try:
                module = importlib.import_module(module_name)
                tool_name = tool_file.stem
                logger.debug(f"Module {module_name} imported. Checking for tool function '{tool_name}'.")

                exec_func = getattr(module, tool_name, None)
                if not exec_func:
                    logger.warning(f"Execution function '{tool_name}' NOT found in module {module_name}.")
                elif not callable(exec_func):
                    logger.warning(f"Found '{tool_name}' in {module_name}, but it is not a callable function.")

                get_def_func = getattr(module, "get_tool_definition", None)
                if not get_def_func:
                    logger.warning(f"get_tool_definition function NOT found in module {module_name}.")
                elif not callable(get_def_func):
                    logger.warning(f"Found get_tool_definition in {module_name}, but it is not a callable function.")

                if get_def_func and callable(get_def_func) and exec_func and callable(exec_func):
                    definition = get_def_func()
                    definition['function']['name'] = tool_name
                    self.tools[tool_name] = {
                        "definition": definition,
                        "function": exec_func
                    }
                    logger.info(f"Successfully loaded tool: {tool_name}")
                else:
                    logger.warning(f"Could not load tool from {tool_file.name} due to missing or invalid functions.")
            except Exception as e:
                logger.error(f"Failed to load tool from {module_name}: {e}", exc_info=True)

    def get_tool_definitions(self, tool_names: list) -> list:
        """Returns the definitions for a list of specified tools."""
        defs = []
        for name in tool_names:
            if name in self.tools:
                defs.append(self.tools[name]['definition'])
            else:
                logger.warning(f"Avatar requested non-existent tool: {name}")
        return defs

    def execute_tool(self, tool_name: str, **kwargs):
        """Executes a tool with the given arguments."""
        if tool_name not in self.tools:
            return f"Error: Tool '{tool_name}' not found."
        
        try:
            logger.info(f"Executing tool '{tool_name}' with args: {kwargs}")
            tool_func = self.tools[tool_name]['function']
            return tool_func(**kwargs)
        except Exception as e:
            logger.error(f"Error executing tool '{tool_name}': {e}")
            return f"Error: {e}"

# Global instance of the tool manager
tool_manager = ToolManager()
