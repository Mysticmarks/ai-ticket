from ai_ticket import find_name


def test_find_name_with_entrepreneur_gpt_string():
    test_string = (
        "```"
        '{"messages":[{"role":"system","content":"You are Entrepreneur-GPT, an AI built to help."},'
        '{"role":"user","content":"Hello"}]}'
    )

    assert find_name(test_string) == "Entrepreneur-GPT"


def test_find_name_without_backticks():
    test_string = (
        '{"messages":[{"role":"system","content":"You are Galaxy-GPT, master of the stars."}]}'
    )

    assert find_name(test_string) == "Galaxy-GPT"


def test_find_name_returns_none_for_non_matching_text():
    assert find_name("Just a regular string") is None


def test_find_name_returns_none_for_non_string_input():
    assert find_name({"messages": []}) is None
