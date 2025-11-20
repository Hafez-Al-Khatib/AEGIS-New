from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
from PIL import Image
import torch

# We use the 2B model because it's lightweight but excellent at OCR
MODEL_ID = "Qwen/Qwen2-VL-2B-Instruct"

class VisionAgent:
    _instance = None
    
    def __init__(self):
        print("Loading Ingestor Agent (Qwen2-VL)...")
        # Load efficiently on GPU if available, else CPU
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        self.model = Qwen2VLForConditionalGeneration.from_pretrained(
            MODEL_ID, 
            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
            device_map="auto"
        )
        self.processor = AutoProcessor.from_pretrained(MODEL_ID)
        print("Ingestor Agent Ready.")

    def analyze_image(self, image_path: str, prompt_text: str = "Extract all text from this image."):
        image = Image.open(image_path)
        
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt_text},
                ],
            }
        ]
        
        # Prepare inputs
        text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = self.processor(
            text=[text],
            images=image_inputs,
            padding=True,
            return_tensors="pt",
        ).to(self.device)

        # Generate output
        generated_ids = self.model.generate(**inputs, max_new_tokens=128)
        output_text = self.processor.batch_decode(
            generated_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )
        
        return output_text[0]

# Singleton to prevent reloading model constantly
vision_agent = VisionAgent()

def extract_medical_text(image_path: str) -> str:
    # Specialized prompt for medical records
    prompt = """
    Analyze this medical document. Extract the following fields into a JSON format:
    - Patient Name
    - Date
    - Test Names
    - Results/Values
    - Reference Ranges
    """
    return vision_agent.analyze_image(image_path, prompt)