from code_index_mcp.search.ranking import SearchRanker


def test_exact_symbol_match_ranks_first():
    results = [
        {
            "entity_id": "1",
            "name": "other_validate_token",
            "score": 1,
        },
        {
            "entity_id": "2",
            "name": "validate_token",
            "score": 1,
        },
    ]

    ranked = SearchRanker().rank(
        "validate_token",
        results,
    )

    assert ranked[0]["entity_id"] == "2"
