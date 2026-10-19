import base64
import unittest
from pathlib import Path

from app.adapters.comfyui import (
    ComfyUIError,
    attach_ref_images,
    build_prompt,
    choose_video_workflow,
    fit_h3_length,
    fit_h3_side,
    load_image_ref,
    load_workflow,
    plan_video_workflow,
)


class ChooseVideoWorkflowTest(unittest.TestCase):
    def test_text_defaults_to_h3(self) -> None:
        self.assertEqual(choose_video_workflow(None, has_image=False), "t2v.u03")
        self.assertEqual(choose_video_workflow("t2v.u03", has_image=False), "t2v.u03")

    def test_image_switches_to_i2v(self) -> None:
        self.assertEqual(choose_video_workflow("t2v.u03", has_image=True), "t2v.i2v")
        self.assertEqual(choose_video_workflow("minimax_h3_img2vid", has_image=True), "minimax_h3_img2vid")

    def test_i2v_without_image_fails(self) -> None:
        with self.assertRaises(ComfyUIError):
            choose_video_workflow("t2v.i2v", has_image=False)


class PlanVideoWorkflowTest(unittest.TestCase):
    def test_play_modes(self) -> None:
        self.assertEqual(plan_video_workflow("text", "t2v.u03", has_image=False), ("t2v.u03", False))
        self.assertEqual(plan_video_workflow("first_frame", "t2v.u03", has_image=True), ("t2v.i2v", True))
        self.assertEqual(
            plan_video_workflow("first_last_frame", "t2v.u03", has_image=True, has_end_image=True),
            ("t2v.flf2v", True),
        )
        self.assertEqual(plan_video_workflow("multi", "t2v.u03", has_image=False, image_count=3), ("t2v.r2v", True))
        self.assertEqual(fit_h3_length(5, 24, 73), 124)
        self.assertEqual(fit_h3_length(10, 24, 73), 243)
        self.assertEqual(fit_h3_length(30, 24, 73), 243)
        self.assertEqual(fit_h3_side(1280, 768), 1280)
        self.assertEqual(fit_h3_side(1920, 768), 1344)

    def test_unsupported_modes(self) -> None:
        with self.assertRaises(ComfyUIError):
            plan_video_workflow("first_last_frame", "t2v.u03", has_image=True)
        with self.assertRaises(ComfyUIError):
            plan_video_workflow("first_last_frame", "t2v.u03", has_image=False, has_end_image=True)
        with self.assertRaises(ComfyUIError):
            choose_video_workflow("t2v.flf2v", has_image=True, has_end_image=False)
        with self.assertRaises(ComfyUIError):
            plan_video_workflow("multi", "t2v.u03", has_image=False, image_count=1)
        with self.assertRaises(ComfyUIError):
            plan_video_workflow("omni", "t2v.u03", has_image=True)
        with self.assertRaises(ComfyUIError):
            plan_video_workflow("first_frame", "t2v.u03", has_image=False)


class LoadImageRefTest(unittest.TestCase):
    def test_png_data_url(self) -> None:
        raw = base64.b64encode(b"png-bytes").decode()
        data, name = load_image_ref(f"data:image/png;base64,{raw}")
        self.assertEqual(data, b"png-bytes")
        self.assertEqual(name, "input.png")

    def test_rejects_unknown_mime(self) -> None:
        with self.assertRaises(ComfyUIError):
            load_image_ref("data:image/gif;base64,aGk=")

    def test_stem_names_first_and_last(self) -> None:
        raw = base64.b64encode(b"png-bytes").decode()
        _, first = load_image_ref(f"data:image/png;base64,{raw}", stem="first")
        _, last = load_image_ref(f"data:image/jpeg;base64,{raw}", stem="last")
        self.assertEqual(first, "first.png")
        self.assertEqual(last, "last.jpg")


class FlfWorkflowTest(unittest.TestCase):
    def test_last_frame_is_injected(self) -> None:
        path = Path(__file__).resolve().parents[2] / "workflows" / "minimax_h3_flf2vid.json"
        workflow = load_workflow(path)
        graph = build_prompt(
            workflow,
            {"image_name": "first.png", "last_image_name": "last.png", "seed": 7},
        )
        self.assertEqual(graph["20"]["inputs"]["image"], "first.png")
        self.assertEqual(graph["21"]["inputs"]["image"], "last.png")
        self.assertEqual(graph["8"]["inputs"]["first_frame"], ["20", 0])
        self.assertEqual(graph["8"]["inputs"]["last_frame"], ["21", 0])
        self.assertEqual(graph["8"]["class_type"], "MiniMaxH3ImageToVideo")


class RefWorkflowTest(unittest.TestCase):
    def test_refs_attach_in_order(self) -> None:
        path = Path(__file__).resolve().parents[2] / "workflows" / "minimax_h3_ref2vid.json"
        workflow = load_workflow(path)
        graph = build_prompt(workflow, {"seed": 3})
        attach_ref_images(graph, ["ref0.png", "ref1.png"])
        self.assertEqual(graph["8"]["class_type"], "MiniMaxH3ReferenceToVideo")
        self.assertEqual(graph["8"]["inputs"]["ref_images.ref_image_0"], ["30", 0])
        self.assertEqual(graph["8"]["inputs"]["ref_images.ref_image_1"], ["31", 0])
        self.assertEqual(graph["30"]["inputs"]["image"], "ref0.png")
        self.assertEqual(graph["3"]["inputs"]["unet_name"], "minimax_h3_ref2va_pruned_int8_convrot.safetensors")


if __name__ == "__main__":
    unittest.main()
