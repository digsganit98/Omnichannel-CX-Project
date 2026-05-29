def generate_reply(answer: str, channel: str) -> str:
    if channel == "email":
        return f"Hello,\n\n{answer}\n\nRegards,\nCustomer Support"
    return answer
