# -*- coding: utf-8 -*-
"""Attached files in chapters: Word / PPT / PDF / txt / Excel → 课件, mp3 … → audio, mp4 … → video."""
import unittest

from api import decode, manual


def card(card_type="", name="", module="", **extra):
    return {"type": card_type, "job": True, "jobid": "j1", "mid": "m1", "otherInfo": "nodeId_1-x", "jtoken": "t",
            "property": {"name": name, "module": module, **extra}}


class FileKindTest(unittest.TestCase):
    def test_documents(self):
        for name in ("第一章.docx", "教案.doc", "课件.PPTX", "讲义.pdf", "说明.txt", "成绩.xlsx", "资料.wps"):
            self.assertEqual(decode.file_kind(card(name=name)), "document", name)
        self.assertEqual(decode.file_kind(card(module="insertdoc", name="第一章")), "document")
        self.assertEqual(decode.file_kind(card(name="第一章", suffix="pdf")), "document")

    def test_media(self):
        self.assertEqual(decode.file_kind(card(name="听力练习.mp3")), "audio")
        self.assertEqual(decode.file_kind(card(module="insertaudio", name="第二讲")), "audio")
        self.assertEqual(decode.file_kind(card(name="实验演示.mp4")), "video")

    def test_not_a_file(self):
        self.assertEqual(decode.file_kind(card(module="insertbbs", name="讨论")), "")

    def test_labels(self):
        self.assertEqual(decode.file_label(card(name="课件.pptx")), "PPT 课件")
        self.assertEqual(decode.file_label(card(name="讲义.PDF")), "PDF")
        self.assertEqual(decode.file_label(card(name="教案.docx")), "Word 文档")
        self.assertEqual(decode.file_label(card(name="听力.mp3")), "MP3 音频")


class CardRoutingTest(unittest.TestCase):
    def test_files_with_unusual_card_types_are_handled(self):
        jobs = decode._process_attachment_cards([
            card("insertdoc", "第一章教案.docx"),
            card("attachment", "期末复习.pdf"),
            card("insertaudio", "英语听力.mp3", module="insertaudio"),
            card("insertbbs", "讨论一"),
        ])
        self.assertEqual([j["type"] for j in jobs], ["document", "document", "video", "other"])
        self.assertEqual(jobs[0]["file_label"], "Word 文档")
        self.assertEqual(jobs[2]["media"], "Audio")

    def test_document_card_gets_a_label(self):
        jobs = decode._process_attachment_cards([card("document", "第三章.pptx")])
        self.assertEqual((jobs[0]["type"], jobs[0]["file_label"]), ("document", "PPT 课件"))


class ManualLabelTest(unittest.TestCase):
    def test_file_label_in_the_manual_list(self):
        self.assertEqual(manual.kind_label({"type": "document", "file_label": "PDF"}), "PDF")
        self.assertEqual(manual.kind_label({"type": "document"}), "文档 / 课件")


if __name__ == "__main__":
    unittest.main()
