"""이력서 원문의 위치를 보존하는 개인정보 가리기 도구."""

from .mask import MaskedSpan, MaskResult, mask_pii, overlaps_mask

__all__ = ["MaskedSpan", "MaskResult", "mask_pii", "overlaps_mask"]
