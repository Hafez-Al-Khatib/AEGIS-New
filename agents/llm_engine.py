import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Try to use Gemini API if available, otherwise fall back to local model
USE_GEMINI = os.getenv("GOOGLE_API_KEY") is not None

if USE_GEMINI:
    import google.generativeai as genai
    
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    print("Using Gemini API for medical analysis")
else:
    try:
        from llama_cpp import Llama
        print("Using local Qwen2.5-7B model")
    except ImportError:
        print("Warning: llama_cpp not found. Local LLM will not work.")
        Llama = None
    
    MODEL_PATH = "agents\\models\\qwen2.5-7b-instruct-q8_0-00001-of-00003.gguf"

class MedicalLLM:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None and not USE_GEMINI:
            if Llama is None:
                raise ImportError("llama_cpp not installed")
            print("Loading Qwen2.5-7B on GPU... this might take a minute.")
            cls._instance = Llama(
                model_path=MODEL_PATH,
                n_ctx=8192,              # Increased context window
                n_threads=8,             # More threads for CPU offload
                n_gpu_layers=-1,         # Offload ALL layers to GPU
                n_batch=512,             # Larger batch for GPU
                use_mlock=True,          # Lock model in RAM to prevent swapping
                use_mmap=True,           # Memory-map the model file
                verbose=True,            # Show what device is being used
            )
            print("Qwen2.5-7B Loaded on GPU.")
        return cls._instance

def generate_medical_response(prompt: str, max_tokens=512, temperature=0.1):
    if USE_GEMINI:
        # Use Gemini API
        try:
            model = genai.GenerativeModel('gemini-2.0-flash')
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                )
            )
            result = response.text.strip()
            
            print(f"[DEBUG LLM] Gemini response length: {len(result)} chars")
            print(f"[DEBUG LLM] Response preview (first 300 chars): {result[:300]}")
            
            return result
        except Exception as e:
            print(f"[ERROR] Gemini API failed: {e}")
            return "Error: Unable to generate response from Gemini API."
    else:
        # Use local Meditron model
        llm = MedicalLLM.get_instance()
        output = llm(
            prompt,
            max_tokens=max_tokens,
            stop=["</s>", "\n\n\n\n", "</system>", "INSTRUCTIONS:"],
            echo=False,
            temperature=temperature,
            top_p=1.0,
            repeat_penalty=1.1
        )
        result = output['choices'][0]['text'].strip()
        
        print(f"[DEBUG LLM] Raw response length: {len(result)} chars")
        print(f"[DEBUG LLM] Raw response preview (first 300 chars): {result[:300]}")
        print(f"[DEBUG LLM] Raw response preview (last 300 chars): {result[-300:]}")
        
        return result

def analyze_medical_image(image_data: bytes, prompt: str = "Analyze this medical image.") -> str:
    """
    Analyzes a medical image using Gemini 1.5 Pro Vision.
    """
    if not USE_GEMINI:
        return "Error: Vision analysis requires Gemini API key."
        
    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Create image part
        image_part = {
            "mime_type": "image/jpeg",
            "data": image_data
        }
        
        response = model.generate_content(
            [prompt, image_part],
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=1024,
                temperature=0.1,
            )
        )
        
        result = response.text.strip()
        print(f"[DEBUG VISION] Analysis result: {result[:100]}...")
        return result
        
    except Exception as e:
        print(f"[ERROR] Vision analysis failed: {e}")
        return f"Error analyzing image: {e}"