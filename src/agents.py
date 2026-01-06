# ------------------------------------------------------------------------
# agents.py
# contains the definition of the Orchestrator Agent
# 2026-01-05 - S. Kotsonis
# ------------------------------------------------------------------------

from smolagents import ToolCallingAgent
from .tools import (
    inventory_manager_tool,
    quoting_agent_tool,
    finalize_sale_tool,
)

# ------------------------------------------------------------------------
# ORCHESTRATOR AGENT
# I am defining the orchestrator agent that will manage the workflow
# as a ToolCallingAgent that uses the other agents as tools.
# note that the tools provided spin up a separate agent, so that we are not
# asking the same agent to work on two different requests when parallelized
# ------------------------------------------------------------------------

class OrchestratorAgent(ToolCallingAgent):
    def __init__(self, model):
        agent_tools = [inventory_manager_tool, finalize_sale_tool, quoting_agent_tool]
        
        super().__init__(
            model=model,
            name="orchestrator_agent",
            description="Sales Orchestrator",
            instructions="""
            **CONTEXT:**
            You have a `request_date`. Use it EXACTLY for every tool call.
            
            **THE LAWS OF SELLING:**
            
            1. **Availability Law**: Check `inventory_manager_tool`. If *some* items are found, PROCEED with those. Only stop if *everything* is missing.
            
            2. **Pricing Law**: Use `quoting_agent_tool` to get a Total Price.
            
            3. **Transaction Law**: Use `finalize_sale_tool` to record the sale.
            
            **EXECUTION PROTOCOL:**
            - **Sequential**: Availability -> Pricing -> Recording.
            - **Anti-Panic**: Wait for tool outputs. Do not multitask.
            - **Reporting**: Your Final Answer must be DETAILED.
              - BAD: "Sale recorded."
              - GOOD: "Thank you for your order ! Successfully ordered 500 A4 Paper ($25.00) and 200 Pens ($10.00). Total: $35.00. Delivery on 2025-04-10. Balloons were unavailable."
            """,
            tools=agent_tools,
            verbosity_level=1,
            max_steps=10,
        )