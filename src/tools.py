# ------------------------------------------------------------------------
# tools.py
# contains the definition of the Agents (as tools) and the tools for each
# that will be used by the orchestrator
# 2026-01-05 - S. Kotsonis
# ------------------------------------------------------------------------

from typing import List, Dict, Union
import json
import re
from smolagents import tool, ToolCallingAgent
from smolagents.models import ChatMessage
from src.config import model 
from src.database import (
    get_stock_level,
    create_transaction,
    get_supplier_delivery_date,
    get_all_inventory,
    get_cash_balance,
    generate_financial_report,
    search_quote_history,
    paper_supplies
)

# ------------------------------------------------------------------------
# HELPER: Semantic Mapping (The "Brain")
# ------------------------------------------------------------------------
def _semantically_map_catalog(search_terms: List[str]) -> Dict[str, str]:
    """
    Helper function to find Catalog items for the user terms.
    It works in steps:
     1: do an exact match or substring match - add what we could not find to unknowns
     2: if we have unknowns, then spin up an LLM to find the equivalent between the 
        valid names and the unknown terms.
    """
    valid_names = [p['item_name'] for p in paper_supplies]
    mapping = {}
    unknowns = []
    
    # 1. Fast exact/substring match
    for term in search_terms:
        clean_term = term.strip()
        if clean_term in valid_names:
            mapping[term] = clean_term
            continue
        
        found = False
        for name in valid_names:
            if clean_term.lower() == name.lower():
                mapping[term] = name
                found = True
                break
        if not found:
            unknowns.append(term)
    
    if not unknowns:
        return mapping

    # 2. LLM Semantic Match for unknown terms
    try:
        prompt = f"""
        Map these User Terms to the Best Matching Catalog Item.
        
        Valid Catalog: {json.dumps(valid_names)}
        User Terms: {json.dumps(unknowns)}
        
        Rules:
        1. Return JSON ONLY: {{"User Term": "Catalog Item"}}
        2. "printer paper" -> "A4 paper"
        3. "construction paper" -> "Colored paper"
        4. "washi tape" -> "Patterned paper"
        5. "streamers" -> "Crepe paper"
        """
        
        messages = [{"role": "user", "content": prompt}]
        response = model(messages)
        content = response.content if isinstance(response, ChatMessage) else str(response)
        
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            ai_mapping = json.loads(json_match.group())
            mapping.update(ai_mapping)
        else:
            for u in unknowns: mapping[u] = "Product Not Found"
    except Exception:
        for u in unknowns: mapping[u] = "Product Not Found"
        
    return mapping


# ------------------------------------------------------------------------
# Inventory manager Agent tool
# spins up an Inventory manager
# note that the tools are wrapped within the inventory manager function
# so that we do not have to guess (or hallucinate) the request date
# Also, the checks are done in batches, to reduce the number of LLM calls
# ------------------------------------------------------------------------
@tool
def inventory_manager_tool(request_text: str, request_date: str) -> str:
    """
    Spins up a dedicated Inventory Agent to handle stock, mapping, and restocking.
    
    Args:
        request_text: The full user request text.
        request_date: The date mentioned in the request (YYYY-MM-DD).
    """
    
    # define inner tools
    @tool
    def map_items_wrapper(search_terms: List[str]) -> str:
        """
        Maps user descriptions to exact Catalog Names using AI.
        
        Args:
            search_terms: List of product descriptions (e.g. ["printer paper"]).
        """
        return json.dumps(_semantically_map_catalog(search_terms))

    @tool
    def check_stock_wrapper(item_names: List[str]) -> str:
        """
        Checks current stock levels for a list of EXACT Catalog Names.
        
        Args:
            item_names: List of exact catalog names.
        """
        results = {}
        for name in item_names:
            if name == "Product Not Found":
                results[name] = 0
                continue
            try:
                df = get_stock_level(name, request_date)
                if df.empty:
                    results[name] = 0
                else:
                    results[name] = int(df['current_stock'].iloc[0]) 
            except Exception:
                results[name] = 0
        return json.dumps(results)

    @tool
    def restock_wrapper(items_to_restock: str) -> str:
        """
        Orders new stock from the supplier.
        
        Args:
            items_to_restock: JSON string {"Catalog Name": quantity}.
        """
        try:
            orders = json.loads(items_to_restock)
            report = []
            price_map = {p['item_name']: p['unit_price'] for p in paper_supplies}
            
            for item_name, qty in orders.items():
                if item_name == "Product Not Found" or item_name not in price_map:
                    report.append(f"Skipped invalid item: {item_name}")
                    continue
                    
                cost = qty * price_map.get(item_name, 0.10)
                create_transaction(item_name, 'stock_orders', qty, cost, request_date)
                delivery_date = get_supplier_delivery_date(request_date, qty)
                report.append(f"Ordered {qty} {item_name} (Arrives: {delivery_date})")
                
            return "\n".join(report)
        except Exception as e:
            return f"Error restocking: {str(e)}"

    @tool
    def check_delivery_wrapper(quantity: int) -> str:
        """
        Checks delivery date for an order placed TODAY.
        
        Args:
            quantity: Total units to order.
        """
        return get_supplier_delivery_date(request_date, quantity)

    @tool
    def audit_inventory_wrapper() -> str:
        """
        Retrieves a full list of all inventory items and their current stock levels.
        Use this if the user asks for a general stock check.
        """
        return json.dumps(get_all_inventory(request_date))

    worker_tools = [map_items_wrapper, check_stock_wrapper, restock_wrapper, check_delivery_wrapper, audit_inventory_wrapper]
    
    system_prompt = f"""
    You are the Inventory Manager.
    SIMULATION CONTEXT: {request_date}.
    
    YOUR JOB:
    1. EXTRACT items from "{request_text}".
    2. CONVERT UNITS (CRITICAL):
       - IF "Ream" or "Reams": Multiply Quantity by 500. (e.g., 500 reams = 250,000 sheets).
       - IF "Box" or "Boxes": Multiply Quantity by 2500.
       - IF "Sheet": Quantity is 1.
    3. MAP: Call 'map_items_wrapper'.
    4. CHECK: Call 'check_stock_wrapper'.
    5. RESTOCK: If (Stock < Needed), order the difference using 'restock_wrapper'.
    6. REPORT: Summarize actions with specific delivery dates.
    
    CRITICAL:
    - Do NOT restock "Product Not Found".
    - ONE STEP AT A TIME. Wait for tool outputs.
    """
    
    agent = ToolCallingAgent(
        tools=worker_tools,
        model=model,
        description=system_prompt,
        max_steps=10
    )
    
    return agent.run(request_text)


# ------------------------------------------------------------------------
# Sales Finisher Agent Tool
# spins up a Sales Finisher Agent
# Its purpose is to check prices, finalize the transaction, and generate reports
# It checks prices in batches to reduce the number of LLM calls
# Same as inventory agent, the order_date is found once and passed within
# to reduce hallucinations
# ------------------------------------------------------------------------
@tool
def finalize_sale_tool(order_details: str, order_date: str) -> str:
    """
    Spins up a Sales Agent to finalize the transaction.
    
    Args:
        order_details: The confirmed list of items to sell.
        order_date: The date of the sale (YYYY-MM-DD).
    """

    @tool
    def finalize_transaction_wrapper(item_name: str, quantity: int, total_price: float) -> str:
        """
        Records a sale.
        
        Args:
            item_name: Exact catalog name.
            quantity: Integer units sold.
            total_price: Revenue as a number (float/int).
        """
        create_transaction(item_name, 'sales', quantity, total_price, order_date)
        return f"Sale Recorded: {quantity} {item_name} for ${total_price}"

    @tool
    def check_prices_batch_wrapper(item_names: List[str]) -> str:
        """
        Gets unit prices for a list of items.
        
        Args:
            item_names: List of product names.
        """
        mapped = _semantically_map_catalog(item_names)
        price_map = {p['item_name']: p['unit_price'] for p in paper_supplies}
        results = {}
        for user_term, catalog_name in mapped.items():
            if catalog_name in price_map:
                results[user_term] = price_map[catalog_name]
            else:
                results[user_term] = 0.0
        return json.dumps(results)

    @tool
    def generate_daily_report_wrapper() -> str:
        """
        Generates a financial report for the current date.
        """
        report = generate_financial_report(order_date)
        return f"Daily Financial Report: Cash Balance=${report['cash_balance']}, Inventory Value=${report['inventory_value']}"

    worker_tools = [finalize_transaction_wrapper, check_prices_batch_wrapper, generate_daily_report_wrapper]
    
    system_prompt = f"""
    You are the Sales Finisher.
    SIMULATION CONTEXT: {order_date}.
    
    YOUR JOB:
    1. Parse "{order_details}".
    2. CHECK PRICES: Call 'check_prices_batch_wrapper' with ALL item names.
    3. CALCULATE: (Quantity * Unit Price) for each item.
    4. FINALIZE: Call 'finalize_transaction_wrapper' using the calculated total.
    
    CRITICAL:
    - SKIP items with $0.0 unit price.
    - 'total_price' must be a float > 0.0.
    - REPORT: List every item sold and the Grand Total revenue.
    """
    
    agent = ToolCallingAgent(
        tools=worker_tools,
        model=model,
        description=system_prompt,
        max_steps=10
    )
    
    return agent.run(order_details) 


# ------------------------------------------------------------------------
# Quoting Agent Tool
# spins up a Quoting Agent
# Its purpose is to check historical quotes and quote the order
# ------------------------------------------------------------------------
@tool
def quoting_agent_tool(request_text: str, request_date: str) -> str:
    """
    Spins up a Quoting Agent to calculate prices.
    
    Args:
        request_text: The user's request.
        request_date: The date of request.
    """
    
    @tool
    def calculate_quote_batch_wrapper(items_json: str) -> str:
        """
        Calculates prices for multiple items at once to avoid loop steps.
        
        Args:
            items_json: JSON string dictionary {"Item Name": quantity}.
        """
        try:
            items = json.loads(items_json)
            price_map = {p['item_name']: p['unit_price'] for p in paper_supplies}
            
            mapped = _semantically_map_catalog(list(items.keys()))
            
            quote_lines = []
            grand_total = 0.0
            
            for user_term, qty in items.items():
                catalog_name = mapped.get(user_term, "Product Not Found")
                if catalog_name == "Product Not Found" or catalog_name not in price_map:
                    quote_lines.append(f"{user_term}: Unavailable")
                    continue
                    
                unit_price = price_map[catalog_name]
                line_total = unit_price * qty
                if qty >= 500: line_total *= 0.90 # Discount
                
                grand_total += line_total
                quote_lines.append(f"{catalog_name} (x{qty}): ${line_total:.2f}")
                
            return json.dumps({"details": quote_lines, "total": round(grand_total, 2)})
        except Exception as e:
            return f"Error: {str(e)}"

    @tool
    def get_historical_quotes_wrapper(keywords: List[str]) -> str:
        """
        Searches past quotes.
        
        Args:
            keywords: Search terms.
        """
        results = search_quote_history(keywords)
        if not results: return "No relevant historical quotes found."
        formatted = []
        for r in results:
            formatted.append(f"Date: {r['order_date']}, Total: ${r['total_amount']}")
        return "\n".join(formatted[:3])

    worker_tools = [get_historical_quotes_wrapper, calculate_quote_batch_wrapper]
    
    system_prompt = f"""
    You are the Quoting Agent.
    SIMULATION CONTEXT: {request_date}.
    
    YOUR JOB:
    1. Identify items/quantities from "{request_text}".
    2. CONVERT UNITS (CRITICAL): 
       - "500 reams" -> 250,000 units. (Multiply reams by 500).
       - "10 boxes" -> 25,000 units. (Multiply boxes by 2500).
       - DO NOT calculate price for "500" if it says "500 reams". You must calculate for 250,000.
    3. CALL 'calculate_quote_batch_wrapper' with the CONVERTED quantities.
    4. REPORT: 
        - Detailed list of prices.
        - Total Quote Amount.
    """
    
    agent = ToolCallingAgent(
        tools=worker_tools,
        model=model,
        description=system_prompt,
        max_steps=10
    )
    
    return agent.run(request_text)