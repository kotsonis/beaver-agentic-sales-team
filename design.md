# Multi-Agent System Design & Reflection
**Project:** Beaver's Choice Paper Company Automation
**Author:** Stefanos Kotsonis

## 1. System Architecture
The system utilizes a hierarchical multi-agent architecture powered by `smolagents` and `gpt-4o-mini`. The design mimics a real-world corporate structure to ensure clear separation of concerns and maintainable logic.

### 1.1 Diagram Description
The workflow follows a top-down orchestration pattern:
1.  **Orchestrator Agent (Office Manager)**: Acts as the single point of entry. It parses the natural language request, extracts the critical context (Simulation Date), and delegates sub-tasks to specialized worker agents.
2.  **Inventory Agent (Warehouse Manager)**: Responsible for physical stock. It maps vague user terms (e.g., "printer paper") to database items, checks levels, and autonomously triggers restock orders if inventory is insufficient.
3.  **Quoting Agent (Sales Rep)**: Responsible for pricing. It calculates costs based on volume (applying bulk discounts) and checks historical data to ensure consistent pricing.
4.  **Sales Agent (Finance)**: Responsible for the ledger. It commits the final transaction to the database and generates financial reports.

### 1.2 Agent Tools
* **Inventory Tools**: 
    * `map_item_to_database`: Uses an LLM call to intelligently map user intent to catalog items (e.g., mapping "shiny paper" to "Glossy paper"). This solved major issues with fuzzy matching failing on synonyms.
    * `check_stock`: Queries the SQLite database for current levels.
    * `restock_inventory`: Automatically purchases stock when low.
    * `audit_inventory`: get the complete inventory.
* **Quoting Tools**: 
    * `calculate_quote`: Applies business logic (10% discount for orders > 500 units).
    * `get_historical_quotes`: Retrieves past context.
* **Sales Tools**: 
    * `finalize_transaction`: Writes the final sale record.
    * `generate_report_tool`: Creates the end-of-day financial summary.

## 2. Evaluation & Reflection
The system was tested against the provided `quote_requests_sample.csv`. 

### 2.1 Success Metrics
* **Accuracy**: The `search_item_in_catalog` tool successfully handled ambiguous inputs like "printer paper" by correctly mapping them to "Standard copy paper" or "A4 paper" depending on context, significantly reducing agent hallucinations.
* **Autonomy**: The Inventory Agent successfully identified stock shortages (e.g., request for 250 sheets when 0 were available) and autonomously triggered a restock order before confirming availability.
* **Financial Integrity**: The Sales Agent correctly updated the cash balance, reflecting both revenue from sales and expenses from restocking.

### 2.2 Improvements Implemented
* **Smart Mapping**: Initially, fuzzy string matching failed on terms like "washi tape". I implemented a "Classifier Tool" pattern where the LLM itself is used as a tool to pick the best match from the catalog. This increased robustness.
* **Loop Prevention**: Agents were initially getting stuck in loops trying to find items. I optimized the system prompts to be more directive ("If stock is low, call restock immediately") and capped `max_steps` to prevent runaway costs.

## 3. Future Improvements
1.  **Parallel Execution**: Currently, the Orchestrator calls agents sequentially (Inventory -> Quote -> Sale). For complex orders with multiple items, asynchronous parallel calls could significantly speed up the response time.
2.  **Dynamic Pricing Strategy**: The current pricing is static. A "Business Analyst" agent could be added to adjust prices dynamically based on real-time stock levels (scarcity pricing) or historical demand trends.