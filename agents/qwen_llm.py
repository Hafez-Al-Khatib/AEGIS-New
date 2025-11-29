"""
Qwen 2.5 7B Instruct - LangChain Compatible Wrapper

This module provides a LangChain-compatible chat model wrapper for Qwen 2.5 7B,
enabling proper tool binding and streaming for the AEGIS system.

Privacy-First: Runs entirely locally, no data leaves the system.
"""

import os
import json
from typing import Any, Dict, List, Optional, Iterator, Union, Mapping
from pydantic import Field

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage,
    AIMessageChunk
)
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.tools import BaseTool

# Model path
MODEL_PATH = os.getenv(
    "QWEN_MODEL_PATH",
    "agents/models/qwen2.5-7b-instruct-q8_0-00001-of-00003.gguf"
)


class QwenChatModel(BaseChatModel):
    """
    LangChain-compatible Chat Model wrapper for Qwen 2.5 7B Instruct.
    
    Features:
    - Proper tool/function calling support
    - Streaming token generation
    - GPU acceleration via llama.cpp
    - Privacy-preserving (runs locally)
    
    Usage:
        llm = QwenChatModel()
        llm_with_tools = llm.bind_tools([tool1, tool2])
        response = llm_with_tools.invoke([HumanMessage(content="Hello")])
    """
    
    model_path: str = Field(default=MODEL_PATH)
    n_ctx: int = Field(default=8192, description="Context window size")
    n_gpu_layers: int = Field(default=-1, description="GPU layers (-1 for all)")
    temperature: float = Field(default=0.1)
    max_tokens: int = Field(default=1024)
    
    _llm: Any = None
    _tools: List[BaseTool] = []
    
    class Config:
        arbitrary_types_allowed = True
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._load_model()
    
    def _load_model(self):
        """Load the Qwen model via llama.cpp"""
        if self._llm is not None:
            return
            
        try:
            from llama_cpp import Llama
            
            print(f"[QWEN] Loading model from {self.model_path}...")
            self._llm = Llama(
                model_path=self.model_path,
                n_ctx=self.n_ctx,
                n_threads=8,
                n_gpu_layers=self.n_gpu_layers,
                n_batch=512,
                use_mlock=True,
                use_mmap=True,
                verbose=False
            )
            print("[QWEN] Model loaded successfully")
            
        except ImportError:
            print("[QWEN] WARNING: llama_cpp not installed. Using mock responses.")
            self._llm = None
        except Exception as e:
            print(f"[QWEN] ERROR loading model: {e}")
            self._llm = None
    
    @property
    def _llm_type(self) -> str:
        return "qwen-2.5-7b-instruct"
    
    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        return {
            "model_path": self.model_path,
            "n_ctx": self.n_ctx,
            "temperature": self.temperature
        }
    
    def bind_tools(self, tools: List[BaseTool], **kwargs) -> "QwenChatModel":
        """
        Bind tools to the model for function calling.
        Returns a new instance with tools bound.
        """
        new_model = QwenChatModel(
            model_path=self.model_path,
            n_ctx=self.n_ctx,
            n_gpu_layers=self.n_gpu_layers,
            temperature=self.temperature,
            max_tokens=self.max_tokens
        )
        new_model._llm = self._llm
        new_model._tools = tools
        return new_model
    
    def _format_messages(self, messages: List[BaseMessage]) -> str:
        """
        Format messages into Qwen chat template.
        
        Qwen uses:
        <|im_start|>system
        {system_message}<|im_end|>
        <|im_start|>user
        {user_message}<|im_end|>
        <|im_start|>assistant
        {assistant_message}<|im_end|>
        """
        formatted = ""
        
        for msg in messages:
            if isinstance(msg, SystemMessage):
                formatted += f"<|im_start|>system\n{msg.content}<|im_end|>\n"
            elif isinstance(msg, HumanMessage):
                formatted += f"<|im_start|>user\n{msg.content}<|im_end|>\n"
            elif isinstance(msg, AIMessage):
                formatted += f"<|im_start|>assistant\n{msg.content}<|im_end|>\n"
            elif isinstance(msg, ToolMessage):
                formatted += f"<|im_start|>tool\n{msg.content}<|im_end|>\n"
        
        # Add assistant prompt for generation
        formatted += "<|im_start|>assistant\n"
        
        return formatted
    
    def _format_tools_prompt(self) -> str:
        """Generate tools description for the prompt."""
        if not self._tools:
            return ""
        
        tools_desc = "\n\nYou have access to the following tools:\n\n"
        
        for tool in self._tools:
            tools_desc += f"- {tool.name}: {tool.description}\n"
            
            # Add input schema if available
            if hasattr(tool, 'args_schema') and tool.args_schema:
                schema = tool.args_schema.schema()
                if 'properties' in schema:
                    tools_desc += f"  Parameters: {json.dumps(schema['properties'], indent=2)}\n"
        
        tools_desc += """
To use a tool, respond with a JSON block:
```json
{
  "tool": "tool_name",
  "tool_input": {"param1": "value1", ...}
}
```

If you don't need to use a tool, just respond normally.
"""
        return tools_desc
    
    def _parse_tool_calls(self, response: str) -> List[Dict[str, Any]]:
        """Parse tool calls from the response."""
        tool_calls = []
        
        # Look for JSON tool calls
        import re
        json_pattern = r'```(?:json)?\s*(\{[^`]+\})\s*```'
        matches = re.findall(json_pattern, response, re.DOTALL)
        
        for match in matches:
            try:
                parsed = json.loads(match)
                if 'tool' in parsed and 'tool_input' in parsed:
                    tool_calls.append({
                        "name": parsed["tool"],
                        "args": parsed["tool_input"],
                        "id": f"call_{len(tool_calls)}"
                    })
            except json.JSONDecodeError:
                continue
        
        return tool_calls
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs
    ) -> ChatResult:
        """Generate a response from the model."""
        
        # Add tools to system message if bound
        if self._tools:
            # Insert tools description into first system message or create one
            tools_prompt = self._format_tools_prompt()
            has_system = any(isinstance(m, SystemMessage) for m in messages)
            
            if has_system:
                messages = [
                    SystemMessage(content=m.content + tools_prompt) if isinstance(m, SystemMessage) else m
                    for m in messages
                ]
            else:
                messages = [SystemMessage(content=tools_prompt)] + list(messages)
        
        prompt = self._format_messages(messages)
        
        if self._llm is None:
            # Mock response for testing without model
            content = "I apologize, but the local LLM is not loaded. Please ensure Qwen model is installed."
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content=content))]
            )
        
        # Generate response
        response = self._llm(
            prompt,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stop=stop or ["<|im_end|>", "<|im_start|>"],
            echo=False
        )
        
        content = response["choices"][0]["text"].strip()
        
        # Parse tool calls if tools are bound
        tool_calls = []
        if self._tools:
            tool_calls = self._parse_tool_calls(content)
        
        # Create AI message
        if tool_calls:
            ai_message = AIMessage(
                content=content,
                tool_calls=tool_calls
            )
        else:
            ai_message = AIMessage(content=content)
        
        return ChatResult(
            generations=[ChatGeneration(message=ai_message)]
        )
    
    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs
    ) -> Iterator[AIMessageChunk]:
        """Stream tokens from the model."""
        
        if self._tools:
            tools_prompt = self._format_tools_prompt()
            has_system = any(isinstance(m, SystemMessage) for m in messages)
            
            if has_system:
                messages = [
                    SystemMessage(content=m.content + tools_prompt) if isinstance(m, SystemMessage) else m
                    for m in messages
                ]
            else:
                messages = [SystemMessage(content=tools_prompt)] + list(messages)
        
        prompt = self._format_messages(messages)
        
        if self._llm is None:
            yield AIMessageChunk(content="LLM not loaded.")
            return
        
        # Stream tokens
        for output in self._llm(
            prompt,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stop=stop or ["<|im_end|>", "<|im_start|>"],
            echo=False,
            stream=True
        ):
            token = output["choices"][0]["text"]
            yield AIMessageChunk(content=token)


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_qwen_instance: Optional[QwenChatModel] = None

def get_qwen_llm() -> QwenChatModel:
    """Get or create the Qwen LLM singleton."""
    global _qwen_instance
    if _qwen_instance is None:
        _qwen_instance = QwenChatModel()
    return _qwen_instance
