from langgraph.graph import StateGraph, MessageState, START, END
from langgraph.prebuilt import ToolNode, tools_condition

def reasoner(state:MessageState):
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}

build = StateGraph(MessageState)