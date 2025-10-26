"""
Streamlit Demo App for AI Service
Supports both text and image input for recipe extraction and conflict detection
"""
import streamlit as st
import json
import base64
from PIL import Image
import io

from app.main import ShoppingCartPipeline

# Page config
st.set_page_config(
    page_title="AI Cooking Assistant",
    page_icon="🍳",
    layout="wide"
)

# Initialize pipeline
@st.cache_resource
def get_pipeline():
    return ShoppingCartPipeline()

pipeline = get_pipeline()

# Title
st.title("🍳 AI Cooking Assistant")
st.markdown("---")

# Sidebar for input selection
with st.sidebar:
    st.header("⚙️ Settings")
    input_mode = st.radio(
        "Select Input Mode:",
        ["Text Input", "Image Input"],
        help="Choose how you want to provide your recipe query"
    )
    
    st.markdown("---")
    st.markdown("### About")
    st.info("""
    This app helps you:
    - Extract dish recipes
    - Detect ingredient conflicts
    - Get replacement suggestions
    - View nutritional warnings
    """)

# Main content
if input_mode == "Text Input":
    st.header("📝 Text Input Mode")
    
    # Text input
    query = st.text_area(
        "Enter your recipe query:",
        placeholder="Example: Hướng dẫn nấu món canh cua với cam vắt vào",
        height=100
    )
    
    # Process button
    if st.button("🔍 Process Query", type="primary", disabled=not query):
        with st.spinner("Processing your query..."):
            try:
                result = pipeline.process(query)
                
                # Display results in tabs
                tab1, tab2, tab3, tab4 = st.tabs(["📊 Summary", "🛒 Cart", "⚠️ Warnings", "📄 Raw JSON"])
                
                with tab1:
                    st.subheader("Summary")
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric("Status", result.get('status', 'N/A').upper())
                    with col2:
                        dish_name = result.get('dish', {}).get('name', 'N/A')
                        st.metric("Dish", dish_name)
                    with col3:
                        cart = result.get('cart', {})
                        st.metric("Total Ingredients", cart.get('total_items', 0))
                
                with tab2:
                    st.subheader("🛒 Shopping Cart")
                    cart_items = result.get('cart', {}).get('items', [])
                    
                    if cart_items:
                        for idx, item in enumerate(cart_items, 1):
                            with st.container():
                                col1, col2, col3 = st.columns([3, 1, 1])
                                with col1:
                                    st.write(f"**{idx}. {item.get('name_vi')}**")
                                    st.caption(f"ID: {item.get('ingredient_id')} | Category: {item.get('category')}")
                                with col2:
                                    qty = item.get('converted_quantity', '')
                                    unit = item.get('converted_unit', '')
                                    st.write(f"{qty} {unit}")
                                with col3:
                                    st.write(f"_{item.get('category', 'N/A')}_")
                                st.divider()
                    else:
                        st.info("No ingredients in cart")
                    
                    # Suggestions
                    suggestions = result.get('suggestions', [])
                    if suggestions:
                        st.subheader("💡 Suggestions")
                        for sug in suggestions[:5]:
                            st.write(f"- {sug.get('name_vi')} ({sug.get('reason', 'N/A')})")
                
                with tab3:
                    st.subheader("⚠️ Warnings & Conflicts")
                    warnings = result.get('warnings', [])
                    
                    if not warnings:
                        st.success("✅ No warnings or conflicts detected!")
                    else:
                        # Separate conflicts from other warnings
                        conflicts = [w for w in warnings if w.get('source') == 'conflict']
                        other_warnings = [w for w in warnings if w.get('source') != 'conflict']
                        
                        # Display conflicts
                        if conflicts:
                            st.error(f"🚫 {len(conflicts)} Conflict(s) Detected")
                            
                            for idx, conflict in enumerate(conflicts, 1):
                                with st.expander(f"Conflict #{idx}: {conflict.get('severity', 'N/A').upper()}", expanded=True):
                                    details = conflict.get('details', {})
                                    
                                    # Conflicting items
                                    items = details.get('conflicting_items', [])
                                    st.warning(f"**Conflicting Items:** {', '.join(items)}")
                                    
                                    # Message and advice
                                    st.write(f"**Reason:** {details.get('message', 'N/A')}")
                                    st.write(f"**Advice:** {details.get('advice', 'N/A')}")
                                    
                                    # Sources
                                    sources = details.get('sources', [])
                                    if sources:
                                        st.write("**Sources:**")
                                        for src in sources:
                                            st.markdown(f"- [{src.get('name')}]({src.get('url')})")
                                    
                                    # Replacement suggestions
                                    replacements = details.get('replacement_suggestions', [])
                                    if replacements:
                                        st.write("**✨ Replacement Suggestions:**")
                                        cols = st.columns(min(len(replacements), 3))
                                        for i, repl in enumerate(replacements[:3]):
                                            with cols[i]:
                                                st.info(f"**{repl.get('name_vi')}**\n\nID: {repl.get('ingredient_id')}\n\nCategory: {repl.get('category')}")
                        
                        # Display other warnings
                        if other_warnings:
                            st.warning(f"⚡ {len(other_warnings)} Other Warning(s)")
                            for warn in other_warnings:
                                st.write(f"- {warn.get('message', 'N/A')}")
                    
                    # Insights
                    insights = result.get('insights', [])
                    if insights:
                        st.subheader("💬 Insights")
                        for insight in insights:
                            st.info(insight)
                
                with tab4:
                    st.subheader("Raw JSON Output")
                    st.json(result)
                    
                    # Download button
                    json_str = json.dumps(result, ensure_ascii=False, indent=2)
                    st.download_button(
                        label="📥 Download JSON",
                        data=json_str,
                        file_name="recipe_result.json",
                        mime="application/json"
                    )
                
            except Exception as e:
                st.error(f"❌ Error processing query: {str(e)}")
                st.exception(e)

else:  # Image Input
    st.header("🖼️ Image Input Mode")
    
    # File uploader
    uploaded_file = st.file_uploader(
        "Upload an image of a dish or ingredients:",
        type=["jpg", "jpeg", "png"],
        help="Upload a clear image of the dish or ingredients you want to analyze"
    )
    
    # Optional description
    description = st.text_input(
        "Optional description (helps improve accuracy):",
        placeholder="Example: Món canh cua với cam"
    )
    
    if uploaded_file is not None:
        # Display image
        image = Image.open(uploaded_file)
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.image(image, caption="Uploaded Image", use_column_width=True)
        
        with col2:
            st.write("**Image Details:**")
            st.write(f"- Format: {image.format}")
            st.write(f"- Size: {image.size}")
            st.write(f"- Mode: {image.mode}")
        
        # Process button
        if st.button("🔍 Analyze Image", type="primary"):
            with st.spinner("Analyzing image..."):
                try:
                    # Convert image to base64
                    buffered = io.BytesIO()
                    image.save(buffered, format=image.format or "PNG")
                    img_base64 = base64.b64encode(buffered.getvalue()).decode()
                    
                    # Determine mime type
                    mime_type = f"image/{image.format.lower()}" if image.format else "image/png"
                    
                    # Process image
                    result = pipeline.process_image(img_base64, description, mime_type)
                    
                    # Display results in tabs (same structure as text input)
                    tab1, tab2, tab3, tab4 = st.tabs(["📊 Summary", "🛒 Cart", "⚠️ Warnings", "📄 Raw JSON"])
                    
                    with tab1:
                        st.subheader("Summary")
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.metric("Status", result.get('status', 'N/A').upper())
                        with col2:
                            dish_name = result.get('dish', {}).get('name', 'N/A')
                            st.metric("Dish", dish_name)
                        with col3:
                            cart = result.get('cart', {})
                            st.metric("Total Ingredients", cart.get('total_items', 0))
                    
                    with tab2:
                        st.subheader("🛒 Shopping Cart")
                        cart_items = result.get('cart', {}).get('items', [])
                        
                        if cart_items:
                            for idx, item in enumerate(cart_items, 1):
                                with st.container():
                                    col1, col2, col3 = st.columns([3, 1, 1])
                                    with col1:
                                        st.write(f"**{idx}. {item.get('name_vi')}**")
                                        st.caption(f"ID: {item.get('ingredient_id')} | Category: {item.get('category')}")
                                    with col2:
                                        qty = item.get('converted_quantity', '')
                                        unit = item.get('converted_unit', '')
                                        st.write(f"{qty} {unit}")
                                    with col3:
                                        st.write(f"_{item.get('category', 'N/A')}_")
                                    st.divider()
                        else:
                            st.info("No ingredients in cart")
                        
                        # Suggestions
                        suggestions = result.get('suggestions', [])
                        if suggestions:
                            st.subheader("💡 Suggestions")
                            for sug in suggestions[:5]:
                                st.write(f"- {sug.get('name_vi')} ({sug.get('reason', 'N/A')})")
                    
                    with tab3:
                        st.subheader("⚠️ Warnings & Conflicts")
                        warnings = result.get('warnings', [])
                        
                        if not warnings:
                            st.success("✅ No warnings or conflicts detected!")
                        else:
                            # Separate conflicts from other warnings
                            conflicts = [w for w in warnings if w.get('source') == 'conflict']
                            other_warnings = [w for w in warnings if w.get('source') != 'conflict']
                            
                            # Display conflicts
                            if conflicts:
                                st.error(f"🚫 {len(conflicts)} Conflict(s) Detected")
                                
                                for idx, conflict in enumerate(conflicts, 1):
                                    with st.expander(f"Conflict #{idx}: {conflict.get('severity', 'N/A').upper()}", expanded=True):
                                        details = conflict.get('details', {})
                                        
                                        # Conflicting items
                                        items = details.get('conflicting_items', [])
                                        st.warning(f"**Conflicting Items:** {', '.join(items)}")
                                        
                                        # Message and advice
                                        st.write(f"**Reason:** {details.get('message', 'N/A')}")
                                        st.write(f"**Advice:** {details.get('advice', 'N/A')}")
                                        
                                        # Sources
                                        sources = details.get('sources', [])
                                        if sources:
                                            st.write("**Sources:**")
                                            for src in sources:
                                                st.markdown(f"- [{src.get('name')}]({src.get('url')})")
                                        
                                        # Replacement suggestions
                                        replacements = details.get('replacement_suggestions', [])
                                        if replacements:
                                            st.write("**✨ Replacement Suggestions:**")
                                            cols = st.columns(min(len(replacements), 3))
                                            for i, repl in enumerate(replacements[:3]):
                                                with cols[i]:
                                                    st.info(f"**{repl.get('name_vi')}**\n\nID: {repl.get('ingredient_id')}\n\nCategory: {repl.get('category')}")
                            
                            # Display other warnings
                            if other_warnings:
                                st.warning(f"⚡ {len(other_warnings)} Other Warning(s)")
                                for warn in other_warnings:
                                    st.write(f"- {warn.get('message', 'N/A')}")
                        
                        # Insights
                        insights = result.get('insights', [])
                        if insights:
                            st.subheader("💬 Insights")
                            for insight in insights:
                                st.info(insight)
                    
                    with tab4:
                        st.subheader("Raw JSON Output")
                        st.json(result)
                        
                        # Download button
                        json_str = json.dumps(result, ensure_ascii=False, indent=2)
                        st.download_button(
                            label="📥 Download JSON",
                            data=json_str,
                            file_name="image_result.json",
                            mime="application/json"
                        )
                    
                except Exception as e:
                    st.error(f"❌ Error analyzing image: {str(e)}")
                    st.exception(e)
    else:
        st.info("👆 Please upload an image to get started")

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center'>
        <p>Built with ❤️ using Streamlit | AI Cooking Assistant Demo</p>
    </div>
    """,
    unsafe_allow_html=True
)
