from langchain.agents import create_agent

@tool
def find_user(user_id:str) -> list[str]:
    return ["user_id",user_id]

agent = create_agent(
    model = "openai:gpt-4.1-mini",
    tools = [
        find_user
    ],
    system_prompt =(
        "You are an access maangement assistanr"
    )
)

result = agent.invoke(
    {
        "messages": [
            {
                "role": "user",
                "content": (
                    "Find Alice's public groups and list their memebrs"
                )
            }
        ]
    },
    config = {"recursion_limit":20}
)

print (result["messages"][-1].content)