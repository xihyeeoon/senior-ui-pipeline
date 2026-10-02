r"""검사 하나에 모듈 하나. 각 모듈에 run(ctx) 하나뿐이다.

ctx 는 context.AuditContext 다. run() 은 아무것도 돌려주지 않고 ctx 의
fatal · warning · metrics · skipped 에 쌓는다. 부르는 순서는 core.audit() 이
정한다 - 여기서는 이름만 모은다.
"""
from . import (a_completion, b_display, c_dead_controls, d_contrast, e_layout,
               f_language, g_state, h_undefined_class, i_choices)

__all__ = ["a_completion", "b_display", "c_dead_controls", "d_contrast",
           "e_layout", "f_language", "g_state", "h_undefined_class",
           "i_choices"]
