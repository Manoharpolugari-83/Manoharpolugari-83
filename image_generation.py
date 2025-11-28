# app.py
import base64
import requests
import streamlit as st
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from PIL import Image
import io
import time

# ============================================
# 🔐 API KEYS - REPLACE WITH YOUR OWN KEYS
# ============================================
GOOGLE_API_KEY = "AIzaSyATHvFdOetDpqbQ0Bd_kMKJlo_hCW3TH_U"  # Get from: https://aistudio.google.com/
HUGGINGFACE_TOKEN = "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"   # Get from: https://huggingface.co/settings/tokens
# ============================================

# Available models (using new router API)
AVAILABLE_MODELS = {
    "FLUX.1 Schnell (Fast)": "black-forest-labs/FLUX.1-schnell",
    "Stable Diffusion 3.5": "stabilityai/stable-diffusion-3.5-large",
    "Stable Diffusion XL": "stabilityai/stable-diffusion-xl-base-1.0",
    "FLUX.1 Dev": "black-forest-labs/FLUX.1-dev",
}

# Set up Streamlit page
st.set_page_config(
    page_title="Text to Image Generator",
    page_icon="🎨",
    layout="centered"
)

# Custom CSS
st.markdown("""
    <style>
    .stButton>button {
        width: 100%;
        border-radius: 10px;
        height: 50px;
        font-weight: bold;
    }
    .status-box {
        padding: 10px;
        border-radius: 5px;
        margin: 5px 0;
    }
    </style>
""", unsafe_allow_html=True)

st.title("🎨 Text to Image Generator")
st.markdown("Describe an image, and let AI generate it using **Gemini + Stable Diffusion**!")
st.divider()

# Initialize Gemini client
@st.cache_resource
def get_gemini_client():
    """Initialize Gemini client"""
    try:
        if GOOGLE_API_KEY == "YOUR_GOOGLE_GEMINI_API_KEY_HERE":
            return None
        
        llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash",
            google_api_key=GOOGLE_API_KEY,
            temperature=0.7
        )
        return llm
    except Exception as e:
        st.error(f"❌ Error initializing Gemini: {e}")
        return None


# ============================================
# 🆕 NEW HUGGING FACE ROUTER API FUNCTION
# ============================================
def generate_image_hf_router(prompt: str, model_id: str, token: str):
    """
    Generate image using NEW Hugging Face Router API
    Endpoint: https://router.huggingface.co/hf-inference/models/{model_id}
    """
    
    # New Router API URL
    API_URL = f"https://router.huggingface.co/hf-inference/models/{model_id}"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Use-Cache": "false"
    }
    
    # Payload for image generation
    payload = {
        "inputs": prompt,
        "parameters": {
            "negative_prompt": "blurry, low quality, ugly, deformed, distorted, bad anatomy, watermark, text, nsfw",
            "num_inference_steps": 25,
            "guidance_scale": 7.5,
            "width": 1024,
            "height": 1024
        }
    }
    
    try:
        response = requests.post(
            API_URL, 
            headers=headers, 
            json=payload, 
            timeout=180  # 3 minutes timeout
        )
        
        # Check response
        if response.status_code == 200:
            # Check if response is an image
            content_type = response.headers.get('content-type', '')
            if 'image' in content_type:
                image = Image.open(io.BytesIO(response.content))
                return image, None
            else:
                return None, f"❌ Unexpected response type: {content_type}"
        
        elif response.status_code == 401:
            return None, "❌ Invalid Hugging Face token. Please check your token."
        
        elif response.status_code == 403:
            return None, "❌ Access denied. You may need to accept the model's license agreement on Hugging Face."
        
        elif response.status_code == 404:
            return None, f"❌ Model not found: {model_id}"
        
        elif response.status_code == 503:
            try:
                error_json = response.json()
                estimated_time = error_json.get("estimated_time", 30)
                return None, f"⏳ Model is loading. Please wait {int(estimated_time)} seconds and try again."
            except:
                return None, "⏳ Model is loading. Please wait 30-60 seconds and try again."
        
        elif response.status_code == 500:
            return None, "❌ Server error. The model might be overloaded. Try again later."
        
        else:
            try:
                error_msg = response.json().get("error", response.text)
            except:
                error_msg = response.text[:500]
            return None, f"❌ Error ({response.status_code}): {error_msg}"
    
    except requests.exceptions.Timeout:
        return None, "⏱️ Request timed out. The model is taking too long. Try again."
    
    except requests.exceptions.ConnectionError:
        return None, "🌐 Connection error. Check your internet connection."
    
    except Exception as e:
        return None, f"❌ Unexpected error: {str(e)}"


# Alternative: Using Hugging Face Inference Client (if installed)
def generate_image_hf_client(prompt: str, model_id: str, token: str):
    """
    Alternative method using huggingface_hub InferenceClient
    """
    try:
        from huggingface_hub import InferenceClient
        
        client = InferenceClient(
            provider="hf-inference",
            api_key=token
        )
        
        image = client.text_to_image(
            prompt=prompt,
            model=model_id,
            negative_prompt="blurry, low quality, ugly, deformed",
            width=1024,
            height=1024,
            num_inference_steps=25
        )
        
        return image, None
    
    except ImportError:
        return None, "huggingface_hub not installed. Using direct API."
    except Exception as e:
        return None, f"❌ Error: {str(e)}"


# Validate API keys
def validate_keys():
    errors = []
    if GOOGLE_API_KEY == "YOUR_GOOGLE_GEMINI_API_KEY_HERE":
        errors.append("⚠️ Please set your GOOGLE_API_KEY")
    if HUGGINGFACE_TOKEN == "YOUR_HUGGINGFACE_TOKEN_HERE":
        errors.append("⚠️ Please set your HUGGINGFACE_TOKEN")
    return errors


# Check for API key errors
key_errors = validate_keys()
if key_errors:
    for error in key_errors:
        st.error(error)
    
    st.info("""
    ### 🔑 How to get API keys:
    
    **Google Gemini API Key:**
    1. Go to [Google AI Studio](https://aistudio.google.com/)
    2. Click "Get API Key"
    3. Create a new key
    
    **Hugging Face Token:**
    1. Go to [Hugging Face Tokens](https://huggingface.co/settings/tokens)
    2. Create a new token with **"Read"** access
    3. Copy the token (starts with `hf_`)
    """)
    st.stop()

# Get Gemini client
llm = get_gemini_client()

# Initialize session state
if "enhanced_prompt" not in st.session_state:
    st.session_state.enhanced_prompt = ""
if "generated_image" not in st.session_state:
    st.session_state.generated_image = None

# Main input area
st.subheader("📝 Enter Your Image Description")
prompt = st.text_area(
    label="Description",
    placeholder="A majestic dragon flying over a medieval castle at sunset, fantasy art style, highly detailed...",
    height=100,
    label_visibility="collapsed"
)

# Model selection
st.subheader("🤖 Select Model")
selected_model_name = st.selectbox(
    "Choose an image generation model:",
    list(AVAILABLE_MODELS.keys()),
    index=0,
    help="FLUX.1 Schnell is fastest, SD 3.5 has best quality"
)
selected_model_id = AVAILABLE_MODELS[selected_model_name]

# Show model info
model_info = {
    "FLUX.1 Schnell (Fast)": "⚡ Fastest generation, good quality",
    "Stable Diffusion 3.5": "🎨 Best quality, slower",
    "Stable Diffusion XL": "🖼️ Great balance of speed and quality",
    "FLUX.1 Dev": "🔬 Development version, experimental"
}
st.caption(model_info.get(selected_model_name, ""))

# Style selection
st.subheader("🎭 Select Style (Optional)")
style_options = [
    "None",
    "Photorealistic",
    "Digital Art",
    "Oil Painting",
    "Watercolor",
    "Anime/Manga",
    "3D Render",
    "Cyberpunk",
    "Fantasy Art",
    "Minimalist",
    "Vintage/Retro",
    "Comic Book",
    "Impressionist",
    "Pop Art"
]
selected_style = st.selectbox("Choose a style:", style_options)

# Action buttons
st.subheader("🚀 Actions")
col1, col2 = st.columns(2)

with col1:
    enhance_btn = st.button("✨ Enhance Prompt", use_container_width=True)

with col2:
    generate_btn = st.button("🖼️ Generate Image", type="primary", use_container_width=True)

st.divider()

# Function to enhance prompt using Gemini
def enhance_prompt_with_gemini(original_prompt: str, style: str) -> str:
    """Use Gemini to enhance the image prompt"""
    if not llm:
        return original_prompt
    
    style_instruction = f"Apply a {style} artistic style." if style != "None" else ""
    
    enhancement_prompt = f"""
    You are an expert at writing prompts for AI image generation models like Stable Diffusion and FLUX.
    
    Enhance the following image description to create a detailed, vivid prompt.
    Include specific details about:
    - Lighting (golden hour, dramatic, soft, etc.)
    - Atmosphere and mood
    - Colors and color palette
    - Composition and camera angle
    - Textures and materials
    - Background elements
    - Quality tags (highly detailed, 8k, masterpiece, etc.)
    {style_instruction}
    
    Keep the enhanced prompt under 150 words, focused and effective.
    Only return the enhanced prompt text, nothing else.
    
    Original description: {original_prompt}
    """
    
    message = HumanMessage(content=enhancement_prompt)
    response = llm.invoke([message])
    return response.content.strip()

# Handle Enhance Prompt button
if enhance_btn:
    if not prompt.strip():
        st.warning("⚠️ Please enter a description first!")
    elif not llm:
        st.warning("⚠️ Gemini API not configured. Using original prompt.")
        # Add style to prompt manually
        if selected_style != "None":
            st.session_state.enhanced_prompt = f"{prompt}, {selected_style} style, highly detailed, professional quality"
        else:
            st.session_state.enhanced_prompt = f"{prompt}, highly detailed, professional quality"
    else:
        with st.spinner("✨ Enhancing your prompt with Gemini AI..."):
            try:
                enhanced = enhance_prompt_with_gemini(prompt, selected_style)
                st.session_state.enhanced_prompt = enhanced
                st.success("✅ Prompt enhanced successfully!")
            except Exception as e:
                st.error(f"❌ Error enhancing prompt: {e}")
                st.session_state.enhanced_prompt = prompt

# Display enhanced prompt if available
if st.session_state.enhanced_prompt:
    st.subheader("📄 Enhanced Prompt")
    st.info(st.session_state.enhanced_prompt)
    
    # Option to edit enhanced prompt
    edited_prompt = st.text_area(
        "Edit enhanced prompt (optional):",
        value=st.session_state.enhanced_prompt,
        height=100,
        key="edit_prompt"
    )
    if edited_prompt != st.session_state.enhanced_prompt:
        st.session_state.enhanced_prompt = edited_prompt

# Handle Generate Image button
if generate_btn:
    # Determine which prompt to use
    final_prompt = st.session_state.enhanced_prompt if st.session_state.enhanced_prompt else prompt
    
    # Add style to prompt if selected and not already enhanced
    if selected_style != "None" and not st.session_state.enhanced_prompt:
        final_prompt = f"{final_prompt}, {selected_style} style, highly detailed, professional quality, 8k"
    
    if not final_prompt.strip():
        st.warning("⚠️ Please enter a description or enhance a prompt first!")
    else:
        progress_bar = st.progress(0, text="🎨 Initializing...")
        status_text = st.empty()
        
        status_text.text(f"🎨 Generating image with {selected_model_name}...")
        progress_bar.progress(25, text="📡 Sending request to Hugging Face...")
        
        # Try the new router API first
        image, error = generate_image_hf_router(final_prompt, selected_model_id, HUGGINGFACE_TOKEN)
        
        progress_bar.progress(75, text="🖼️ Processing image...")
        
        if image:
            progress_bar.progress(100, text="✅ Complete!")
            
            # Save image
            img_path = "generated_image.png"
            image.save(img_path, "PNG")
            st.session_state.generated_image = img_path
            
            status_text.empty()
            progress_bar.empty()
            st.success("✅ Image generated successfully!")
        else:
            progress_bar.empty()
            status_text.empty()
            st.error(error)
            
            # Show troubleshooting tips
            with st.expander("💡 Troubleshooting Tips", expanded=True):
                st.markdown("""
                **Common Solutions:**
                
                1. **Invalid Token (401 Error)**
                   - Go to [Hugging Face Tokens](https://huggingface.co/settings/tokens)
                   - Create a **new token** with **"Read"** access
                   - Make sure it starts with `hf_`
                
                2. **Access Denied (403 Error)**
                   - Some models require you to accept their license
                   - Visit the model page on Hugging Face
                   - Click **"Agree and access repository"**
                   - Models that may require this:
                     - [FLUX.1-schnell](https://huggingface.co/black-forest-labs/FLUX.1-schnell)
                     - [SD 3.5](https://huggingface.co/stabilityai/stable-diffusion-3.5-large)
                
                3. **Model Loading (503 Error)**
                   - Free tier models need to "wake up"
                   - Wait **30-60 seconds** and try again
                   - Try "FLUX.1 Schnell" - it's usually faster
                
                4. **Timeout Error**
                   - The model is overloaded
                   - Try a different model
                   - Try again in a few minutes
                """)

# Display generated image
if st.session_state.generated_image:
    st.subheader("🖼️ Generated Image")
    st.image(st.session_state.generated_image, use_container_width=True)
    
    # Download button
    with open(st.session_state.generated_image, "rb") as f:
        image_data = f.read()
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.download_button(
            label="📥 Download Image",
            data=image_data,
            file_name="ai_generated_image.png",
            mime="image/png",
            use_container_width=True
        )
    
    # Clear button
    if st.button("🗑️ Clear & Start Over"):
        st.session_state.enhanced_prompt = ""
        st.session_state.generated_image = None
        st.rerun()

# Sidebar
with st.sidebar:
    st.header("📖 How to Use")
    st.markdown("""
    1. **Enter** a description of the image
    2. **Select** a model and art style
    3. Click **Enhance Prompt** (optional)
    4. Click **Generate Image**
    5. **Download** your image
    """)
    
    st.divider()
    
    st.header("🔧 API Status")
    
    # Test Hugging Face connection
    if HUGGINGFACE_TOKEN != "YOUR_HUGGINGFACE_TOKEN_HERE":
        try:
            test_url = "https://huggingface.co/api/whoami-v2"
            test_headers = {"Authorization": f"Bearer {HUGGINGFACE_TOKEN}"}
            test_response = requests.get(test_url, headers=test_headers, timeout=5)
            
            if test_response.status_code == 200:
                user_info = test_response.json()
                username = user_info.get('name', 'Connected')
                st.success(f"✅ HF: {username}")
            else:
                st.error("❌ HF: Invalid Token")
        except:
            st.warning("⚠️ HF: Cannot verify")
    
    if llm:
        st.success("✅ Gemini: Connected")
    else:
        st.warning("⚠️ Gemini: Not configured")
    
    st.divider()
    
    st.header("🎯 Model Guide")
    st.markdown("""
    | Model | Speed | Quality |
    |-------|-------|---------|
    | FLUX.1 Schnell | ⚡⚡⚡ | ⭐⭐⭐ |
    | SD XL | ⚡⚡ | ⭐⭐⭐⭐ |
    | SD 3.5 | ⚡ | ⭐⭐⭐⭐⭐ |
    | FLUX.1 Dev | ⚡⚡ | ⭐⭐⭐⭐ |
    """)
    
    st.divider()
    
    st.header("💡 Pro Tips")
    st.markdown("""
    - Be **specific** and **detailed**
    - Include **lighting** descriptions
    - Mention **art style** explicitly
    - Add quality tags like "8k, masterpiece"
    - Use **Enhance Prompt** for better results!
    """)