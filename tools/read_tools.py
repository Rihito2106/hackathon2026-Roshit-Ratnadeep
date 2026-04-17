from tools.data_loader import load_json, DATA_DIR

def get_order(order_id: str) -> dict | str:
    """Fetches order details by order_id."""
    orders = load_json("orders.json")
    
    # Defensive programming: If data is a list of dicts, search it.
    if isinstance(orders, list):
        for order in orders:
            if order.get("order_id") == order_id:
                return order
                
    return f"Order {order_id} not found."

def get_customer(email: str) -> dict | str:
    """Fetches customer profile and tier by email."""
    customers = load_json("customers.json")
    
    if isinstance(customers, list):
        for customer in customers:
            if customer.get("email") == email:
                return customer
                
    return f"Customer with email {email} not found."

def get_product(product_id: str) -> dict | str:
    """Fetches product metadata, category, and warranty by product_id."""
    products = load_json("products.json")
    
    if isinstance(products, list):
        for product in products:
            if product.get("product_id") == product_id:
                return product
                
    return f"Product {product_id} not found."

def search_knowledge_base(query: str) -> str:
    """
    Semantic/Keyword search against the ShopWave policy FAQ.
    Scans the markdown file and returns relevant paragraphs.
    """
    kb_path = DATA_DIR / "knowledge-base.md"
    
    try:
        with open(kb_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        return "🚨 Error: knowledge-base.md file not found."
        
    # Build a simple keyword matcher
    # Filter out tiny words like "a", "is", "the"
    keywords = [kw.lower() for kw in query.split() if len(kw) > 3]
    
    # Split the markdown into paragraphs
    paragraphs = content.split('\n\n')
    results = []
    
    for p in paragraphs:
        # If any significant keyword is in this paragraph, save it
        if any(kw in p.lower() for kw in keywords):
            results.append(p.strip())
            
    if results:
        # Return the top 3 most relevant paragraphs to save LLM context window
        return "\n...\n".join(results[:3])
        
    return f"No relevant policy found for query: '{query}'. Try different keywords."