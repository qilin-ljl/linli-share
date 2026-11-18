import services.visual_analysis_service as vas
from services.visual_analysis_service import _visible_analysis, analyze_batch, analyze_item


def test_visible_analysis_normalizes_category():
    raw = {
        'product_type': '空气炸锅',
        'category': '厨房小家电',
        'brand': '示例品牌',
        'model': 'X1',
        'condition': 'GOOD',
        'condition_score': 4,
        'visible_defects': ['轻微划痕'],
        'visible_accessories': ['炸篮'],
        'unknowns': ['功能状态'],
    }
    result = _visible_analysis(raw)
    assert result['category'] == '家电'
    assert result['condition'] == 'GOOD'
    assert result['condition_score'] == 4
    assert result['unknowns'] == ['功能状态']


def test_analyze_item_returns_vision_result_when_available(monkeypatch):
    def fake_vision(prompt, images):
        return {
            'product_type': '台灯',
            'category': '厨房小家电',
            'brand': None,
            'model': None,
            'condition': 'GOOD',
            'condition_score': 4,
            'visible_defects': [],
            'visible_accessories': ['电源线'],
            'unknowns': ['功能状态'],
        }

    monkeypatch.setattr(vas, '_vision_json', fake_vision)

    result = analyze_item([(b'fake-image', 'image/jpeg')])

    assert result['source'] == 'VISION_API'
    assert result['category'] == '家电'
    assert result['product_type'] == '台灯'


def test_analyze_item_manual_review_when_vision_api_fails(monkeypatch):
    def fake_vision(prompt, images):
        raise RuntimeError('vision unavailable')

    monkeypatch.setattr(vas, '_vision_json', fake_vision)

    result = analyze_item([(b'fake-image', 'image/jpeg')])

    assert result['source'] == 'MANUAL_REVIEW_REQUIRED'
    assert result['product_type'] is None
    assert result['unknowns']


def test_analyze_item_manual_review_when_product_type_missing(monkeypatch):
    def fake_vision(prompt, images):
        return {'category': '家电'}

    monkeypatch.setattr(vas, '_vision_json', fake_vision)

    result = analyze_item([(b'fake-image', 'image/jpeg')])

    assert result['source'] == 'MANUAL_REVIEW_REQUIRED'
    assert result['product_type'] is None
    assert '物品类型' in result['unknowns']


def test_analyze_batch_manual_review_when_no_valid_items(monkeypatch):
    def fake_vision(prompt, images):
        return {'items': []}

    monkeypatch.setattr(vas, '_vision_json', fake_vision)

    result = analyze_batch([(b'fake-image', 'image/jpeg'), (b'fake-image-2', 'image/jpeg')])

    assert result['source'] == 'MANUAL_REVIEW_REQUIRED'
    assert len(result['items']) == 2
    assert result['items'][0]['product_type'] is None
    assert result['items'][1]['unknowns']
