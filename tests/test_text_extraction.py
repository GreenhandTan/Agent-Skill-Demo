from __future__ import annotations

from scripts.browser_adapter import BrowserAdapter


_adapter = BrowserAdapter.__new__(BrowserAdapter)


class TestExtractPrice:
    def test_yuan_sign(self):
        result, val = _adapter._extract_price("¥99.00 索尼耳机")
        assert result == "¥99.00"
        assert val == 99.0

    def test_rmb_sign_with_decimals(self):
        result, val = _adapter._extract_price("价格 ￥299.50 元")
        assert result == "¥299.50"
        assert val == 299.5

    def test_price_with_comma(self):
        result, val = _adapter._extract_price("¥1,234.00")
        assert result == "¥1234.00"
        assert val == 1234.0

    def test_price_range(self):
        result, val = _adapter._extract_price("¥299-499")
        assert result == "¥299.00"
        assert val == 299.0

    def test_price_with_tilde_range(self):
        result, val = _adapter._extract_price("¥500~800")
        assert val == 500.0

    def test_price_unit_yuan(self):
        result, val = _adapter._extract_price("199 元")
        assert val == 199.0

    def test_price_qi_prefix(self):
        result, val = _adapter._extract_price("价格：88.88起")
        assert val == 88.88

    def test_no_price(self):
        result, val = _adapter._extract_price("无价格信息")
        assert result is None
        assert val is None

    def test_zero_price_filtered(self):
        result, val = _adapter._extract_price("¥0.00")
        assert val is None


class TestExtractSalesCount:
    def test_wan_plus_ren_pay(self):
        count = _adapter._extract_sales_count("1.2万+人付款")
        assert count == 12000

    def test_monthly_sales_wan(self):
        count = _adapter._extract_sales_count("月销 3.5万 ")
        assert count == 35000

    def test_plain_sales(self):
        count = _adapter._extract_sales_count("已售 200")
        assert count == 200

    def test_receipt_count(self):
        count = _adapter._extract_sales_count("收货 5000")
        assert count == 5000

    def test_pay_ren(self):
        count = _adapter._extract_sales_count("1000+人付款")
        assert count == 1000

    def test_no_sales(self):
        count = _adapter._extract_sales_count("无销量信息")
        assert count is None


class TestExtractRating:
    def test_haoping_rate(self):
        rating = _adapter._extract_rating("好评率 98.5%")
        assert rating == 0.985

    def test_percent_haoping(self):
        rating = _adapter._extract_rating("95% 好评")
        assert rating == 0.95

    def test_colon_format(self):
        rating = _adapter._extract_rating("好评率：100")
        assert rating == 1.0

    def test_no_rating(self):
        rating = _adapter._extract_rating("无评价信息")
        assert rating is None

    def test_low_rating(self):
        rating = _adapter._extract_rating("好评率 4.8%")
        assert rating == 0.048

    def test_rating_decimal_small(self):
        rating = _adapter._extract_rating("好评率 4.8%")
        assert rating == 0.048


class TestKeywordTokens:
    def test_single_word(self):
        tokens = _adapter._build_keyword_tokens("耳机")
        assert "耳机" in tokens

    def test_short_keyword(self):
        tokens = _adapter._build_keyword_tokens("A")
        assert tokens == ["A"]

    def test_empty_keyword(self):
        tokens = _adapter._build_keyword_tokens("")
        assert tokens == []

    def test_multichar_keyword(self):
        tokens = _adapter._build_keyword_tokens("索尼耳机")
        assert "索尼耳机" in tokens
        assert all(len(t) >= 2 for t in tokens)

    def test_keyword_with_spaces(self):
        tokens = _adapter._build_keyword_tokens("索尼 耳机")
        assert "索尼耳机" in tokens or any("索尼" in t for t in tokens)


class TestMatchesKeyword:
    def test_exact_match(self):
        assert _adapter._matches_keyword("索尼耳机", "", ["索尼耳机"])

    def test_partial_match_in_title(self):
        assert _adapter._matches_keyword("索尼耳机推荐", "", ["索尼"])

    def test_match_in_text(self):
        assert _adapter._matches_keyword("标题", "索尼耳机 正品", ["索尼"])

    def test_no_match(self):
        assert not _adapter._matches_keyword("苹果手机", "", ["索尼"])
