"""Paragraph commands must survive saving, copying and undo as editable text."""
import base64
import json
import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPalette, QTextCursor, QTextListFormat, QTextOption
from PySide6.QtWidgets import QApplication, QDialog

from app.inline_images import AuroraImageEditor, image_sources
from app.paragraph_editor import ParagraphEditor
from app.paragraph_format import (PX_PER_CM, add_metadata, document_blocks,
    document_from_html, options, read_metadata, selected_blocks, settings_from_format)
from app.rich_clipboard import interoperable_html, mixed_paragraph_html, rich_text_rtf


class ParagraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.editor = AuroraImageEditor()
        self.commands = ParagraphEditor(self.editor)
        self.editor.setPlainText('Primeiro\nSegundo\nTerceiro')

    def tearDown(self):
        self.editor.deleteLater()
        self.app.processEvents()

    def block(self, index=0):
        return self.editor.document().findBlockByNumber(index)

    def select_blocks(self, first, last):
        cursor = QTextCursor(self.block(first))
        cursor.setPosition(self.block(last).position()+self.block(last).length()-1, QTextCursor.KeepAnchor)
        self.editor.setTextCursor(cursor)

    def test_selection_ending_at_next_block_does_not_format_it(self):
        cursor = QTextCursor(self.block(0))
        cursor.setPosition(self.block(1).position(), QTextCursor.KeepAnchor)
        self.editor.setTextCursor(cursor)
        self.assertEqual([b.blockNumber() for b in selected_blocks(self.editor)], [0])
        self.commands.align('center')
        self.assertTrue(self.block(0).blockFormat().alignment() & Qt.AlignHCenter)
        self.assertFalse(self.block(1).blockFormat().alignment() & Qt.AlignHCenter)
        self.editor.undo()
        self.assertFalse(self.block(0).blockFormat().alignment() & Qt.AlignHCenter)

    def test_precise_measures_survive_save_html_clipboard_and_rtf(self):
        self.editor.selectAll()
        self.commands.apply({'alignment':'justify','left':1.25,'right':.75,'first':-.5,
                             'before':6,'after':8,'line_mode':'multiple','line_value':1.16})
        source = self.editor.toHtml()
        for html in (source, interoperable_html(source)):
            document = document_from_html(html)
            self.assertEqual(document.toPlainText(), self.editor.toPlainText())
            for block in document_blocks(document):
                state = settings_from_format(block.blockFormat())
                for key, value in (('left',1.25),('right',.75),('first',-.5),('before',6),('after',8),('line_value',1.16)):
                    self.assertAlmostEqual(state[key],value,places=5)
                self.assertEqual(state['alignment'],'justify')
        rtf = rich_text_rtf(source).decode('ascii')
        for control in (r'\qj',r'\li709',r'\ri425',r'\fi-283',r'\sb120',r'\sa160',r'\sl278\slmult1'):
            self.assertIn(control,rtf)

    def test_contextual_spacing_survives_partial_copy_and_undo(self):
        self.editor.selectAll()
        self.commands.apply({'before':6,'after':8,'options':{'contextual':True}})
        self.assertEqual(self.block(1).blockFormat().topMargin(),0)
        self.assertEqual(self.block(1).blockFormat().bottomMargin(),0)
        self.select_blocks(1,2)
        payload = self.editor.createMimeDataFromSelection()
        target = AuroraImageEditor()
        try:
            target.insertFromMimeData(payload)
            self.assertEqual(target.toPlainText(),'Segundo\nTerceiro')
            self.assertTrue(options(target.document().begin().blockFormat())['contextual'])
            self.assertEqual(target.document().begin().blockFormat().topMargin(),0)
            target.undo()
            self.assertEqual(target.toPlainText(),'')
            target.redo()
            self.assertEqual(target.toPlainText(),'Segundo\nTerceiro')
        finally:
            target.deleteLater()
        self.editor.undo()
        self.assertFalse(options(self.block().blockFormat()).get('contextual'))

    def test_multilevel_indent_stays_one_list_and_toggle_changes_mode(self):
        self.editor.selectAll()
        self.commands.list(QTextListFormat.ListDecimal,'number')
        self.commands.list(QTextListFormat.ListDecimal,'multilevel',toggle=True)
        self.assertIsNotNone(self.block().textList())
        self.commands.indent(1)
        lists = [b.textList() for b in document_blocks(self.editor.document())]
        self.assertEqual(len({listing.objectIndex() for listing in lists}),1)
        self.assertEqual(lists[0].format().indent(),2)
        self.assertEqual(lists[0].format().style(),QTextListFormat.ListLowerAlpha)
        html = interoperable_html(self.editor.toHtml())
        restored = document_from_html(html)
        self.assertEqual(restored.toPlainText(),self.editor.toPlainText())
        self.assertEqual(restored.begin().textList().format().indent(),2)
        self.commands.indent(-1)
        self.commands.list(QTextListFormat.ListDecimal,'multilevel',toggle=True)
        self.assertIsNone(self.block().textList())

    def test_nested_numbered_and_empty_bullet_paragraphs_keep_order(self):
        self.editor.setPlainText('Raiz\nFilho\n\nFim')
        self.editor.selectAll()
        self.commands.list(QTextListFormat.ListDecimal,'multilevel')
        fmt = self.block().textList().format()
        fmt.setStart(3)
        self.block().textList().setFormat(fmt)
        self.select_blocks(1,2)
        self.commands.indent(1)
        html = interoperable_html(self.editor.toHtml())
        self.assertIn('start="3"',html)
        self.assertEqual(document_from_html(html).toPlainText(),'Raiz\nFilho\n\nFim')
        rtf = rich_text_rtf(self.editor.toHtml()).decode('ascii')
        self.assertIn(r'\levelstartat3',rtf)
        self.assertIn(r'\ilvl1',rtf)
        self.assertEqual(rtf.count(r'{\listtext'),4)

    def test_marks_are_display_only(self):
        text, html = self.editor.toPlainText(), self.editor.toHtml()
        self.commands.show_marks(True)
        self.assertTrue(self.editor.document().defaultTextOption().flags() & QTextOption.ShowLineAndParagraphSeparators)
        self.assertEqual(self.editor.toPlainText(),text)
        self.assertEqual(self.editor.toHtml(),html)
        self.editor.selectAll()
        self.assertEqual(self.editor.createMimeDataFromSelection().text(),text)
        self.commands.show_marks(False)
        self.assertFalse(self.editor.document().defaultTextOption().flags() & QTextOption.ShowTabsAndSpaces)

    def test_pagination_borders_tabs_and_shading_are_saved_and_exported(self):
        self.editor.selectAll()
        self.commands.apply({'heading':2,'page_before':True,'line_mode':'exact','line_value':15,
            'options':{'keep_next':True,'keep_lines':True,'widow_control':False,'no_hyphen':True,
                       'no_line_numbers':True,'mirror':True,'collapsed':True,'text_wrap':'firstlast',
                       'tabs':[{'position':2*PX_PER_CM,'type':'right','leader':1}],'tab_default':48}})
        self.commands.border('all','#123456',1.5)
        self.commands.shade('#fff59d')
        source = self.editor.toHtml()
        restored = document_from_html(source)
        state = settings_from_format(restored.begin().blockFormat())
        self.assertEqual(state['heading'],2)
        self.assertTrue(state['page_before'])
        self.assertAlmostEqual(state['line_value'],15)
        self.assertEqual(restored.begin().blockFormat().background().color().name(),'#fff59d')
        self.assertEqual(state['options']['tabs'][0]['type'],'right')
        self.assertEqual(restored.begin().blockFormat().headingLevel(),0)
        html, rtf = interoperable_html(source), rich_text_rtf(source).decode('ascii')
        for value in ('border-bottom:1.5px solid #123456','background-color:#fff59d','page-break-before:always','page-break-inside:avoid'):
            self.assertIn(value,html)
        for value in (r'\keepn',r'\keep',r'\nowidctlpar',r'\pagebb',r'\outlinelevel1',r'\indmirror',
                      r'\noline',r'\hyphpar0',r'\collapsed',r'\txbxtwfirstlast',r'\tqr\tldot\tx1134',r'\sl-300\slmult0',r'\brdrbtw'):
            self.assertIn(value,rtf)

    def test_sort_preserves_character_formats_images_and_one_undo(self):
        self.editor.setPlainText('Zulu\nÁrvore\nBeta')
        cursor = QTextCursor(self.block(0))
        cursor.select(QTextCursor.BlockUnderCursor)
        fmt = cursor.charFormat();fmt.setFontWeight(700);cursor.mergeCharFormat(fmt)
        self.editor.setTextCursor(QTextCursor(self.block(2)))
        cursor = self.editor.textCursor();cursor.movePosition(QTextCursor.EndOfBlock);self.editor.setTextCursor(cursor)
        image = QImage(8,8,QImage.Format_ARGB32);image.fill(QColor('#ff0000'))
        self.assertTrue(self.editor.insert_image(image))
        before = self.editor.toPlainText()
        self.commands.sort()
        self.assertEqual(self.editor.toPlainText(),'Árvore\nBeta\ufffc\nZulu')
        self.assertEqual(self.editor.document().find('Zulu').charFormat().fontWeight(),700)
        self.assertEqual(len(image_sources(self.editor.toHtml())),1)
        self.editor.undo()
        self.assertEqual(self.editor.toPlainText(),before)
        self.editor.redo()
        self.assertEqual(self.editor.toPlainText(),'Árvore\nBeta\ufffc\nZulu')

    def test_numeric_sort_header_and_table_cell_guard(self):
        self.editor.setPlainText('Preço\n10,5\n2,25\n1.200,00')
        self.commands.sort(numeric=True,header=True)
        self.assertEqual(self.editor.toPlainText(),'Preço\n2,25\n10,5\n1.200,00')
        self.editor.setHtml('<table><tr><td>b</td><td>a</td></tr></table>')
        original = self.editor.toPlainText()
        self.editor.selectAll()
        with self.assertRaisesRegex(ValueError,'mesma área'):
            self.commands.sort()
        self.assertEqual(self.editor.toPlainText(),original)

    def test_sort_numbered_items_preserves_list_and_single_undo(self):
        self.editor.setPlainText('Zulu\nÁrvore\nBeta')
        self.editor.selectAll();self.commands.list(QTextListFormat.ListDecimal,'number')
        self.commands.sort()
        self.assertEqual(self.editor.toPlainText(),'Árvore\nBeta\nZulu')
        self.assertEqual([b.textList().itemText(b) for b in document_blocks(self.editor.document())],['1.','2.','3.'])
        self.editor.undo()
        self.assertEqual(self.editor.toPlainText(),'Zulu\nÁrvore\nBeta')
        self.assertTrue(all(b.textList() is not None for b in document_blocks(self.editor.document())))

    def test_word_shortcuts_only_change_editor_paragraphs(self):
        from PySide6.QtTest import QTest
        self.editor.show();self.editor.activateWindow();self.editor.setFocus();self.app.processEvents()
        QTest.keyClick(self.editor,Qt.Key_E,Qt.ControlModifier)
        self.assertEqual(settings_from_format(self.block().blockFormat())['alignment'],'center')
        QTest.keyClick(self.editor,Qt.Key_M,Qt.ControlModifier)
        self.assertAlmostEqual(settings_from_format(self.block().blockFormat())['left'],1.25)
        QTest.keyClick(self.editor,Qt.Key_2,Qt.ControlModifier)
        self.assertEqual(settings_from_format(self.block().blockFormat())['line_mode'],'double')
        self.assertEqual(self.editor.toPlainText(),'Primeiro\nSegundo\nTerceiro')
        self.editor.hide()

    def test_mixed_image_and_table_structure_is_preserved_with_extra_css(self):
        image = QImage(6,6,QImage.Format_ARGB32);image.fill(Qt.red)
        self.editor.setPlainText('Antes')
        self.editor.moveCursor(QTextCursor.End)
        self.assertTrue(self.editor.insert_image(image))
        source = self.editor.toHtml()
        source = source.replace('</body>','<table><tr><td>Célula</td></tr></table><p>Depois</p></body>')
        self.editor.setHtml(source)
        self.editor.selectAll();self.commands.border('bottom','#123456')
        self.commands.align('center')
        html = mixed_paragraph_html(self.editor.toHtml())
        self.assertIn('<table',html)
        self.assertIn('border-bottom:1px solid #123456',html)
        self.assertEqual(image_sources(html),image_sources(self.editor.toHtml()))
        self.assertEqual(document_from_html(html).toPlainText(),self.editor.toPlainText())
        from app.clipboard_content import expansion_mime
        self.assertIn('border-bottom:1px solid #123456',expansion_mime(self.editor.toPlainText(),self.editor.toHtml()).html())

    def test_paragraph_only_formatting_selects_rich_clipboard(self):
        from app.formatting import has_rich_formatting
        self.assertFalse(has_rich_formatting(self.editor.toHtml()))
        self.commands.align('right')
        self.assertTrue(has_rich_formatting(self.editor.toHtml()))

    def test_metadata_validation_does_not_import_unbounded_or_unknown_values(self):
        bad = base64.urlsafe_b64encode(json.dumps({'version':1,'paragraphs':[[0,{'tabs':[{'position':1e99,'type':'right','leader':99}],
                            'border':'bad','keep_next':'yes','unknown':'value'}],[-1,{}],[True,{}]]}).encode()).decode()
        parsed = read_metadata('<meta name="aurora-paragraphs" content="'+bad+'" />')
        self.assertEqual(len(parsed),1)
        opts = parsed[0][1]
        self.assertEqual(opts['tabs'][0]['position'],4000)
        self.assertEqual(opts['tabs'][0]['leader'],3)
        self.assertNotIn('border',opts);self.assertNotIn('keep_next',opts);self.assertNotIn('unknown',opts)
        self.assertEqual(read_metadata('<meta name="aurora-paragraphs" content="invalid" />'),[])
        self.assertEqual(read_metadata(add_metadata('<p>x</p>',[[0,{}]])).pop()[0],0)


class ParagraphDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_dialog_defaults_tab_stops_and_cancel(self):
        from app.paragraph_dialog import ParagraphDialog, TabStopsDialog
        from app.paragraph_panel import ParagraphPanel
        from app.themes import ThemeController
        editor = AuroraImageEditor();editor.setPlainText('Teste')
        saved = []
        panel = ParagraphPanel(editor)
        theme = ThemeController('dark')
        try:
            dialog = ParagraphDialog(settings_from_format(editor.document().begin().blockFormat()),save_default=lambda value:saved.append(value))
            dialog.left.setValue(1.25);dialog.after.setValue(8)
            dialog._default()
            self.assertEqual(saved[0]['left'],1.25)
            self.assertIn('Padrão salvo',dialog.saved_hint.text())
            dialog.line_mode.setCurrentIndex(dialog.line_mode.findData('exact'))
            self.assertEqual(dialog.line_value.value(),12)
            self.assertEqual(dialog.line_value.suffix(),' pt')
            dialog.show();self.app.processEvents()
            for name in ('dark','light'):
                theme.set_preference(name);self.app.processEvents()
                palette = dialog.preview.palette()
                foreground = palette.color(QPalette.Text).lightness()
                background = palette.color(QPalette.Base).lightness()
                self.assertGreater(abs(foreground-background),100)
            with patch('app.paragraph_panel.ParagraphDialog',return_value=dialog), patch.object(dialog,'exec',return_value=QDialog.Rejected):
                panel.open_dialog()
            self.assertEqual(settings_from_format(editor.document().begin().blockFormat())['left'],0)
            tab = TabStopsDialog({})
            tab.position.setValue(2);tab.leader.setCurrentIndex(1);tab._define()
            self.assertAlmostEqual(tab.value()['tabs'][0]['position'],2*PX_PER_CM)
            tab._clear();tab.accept()
            self.assertEqual(tab.value()['tabs'],[])
            tab.deleteLater();dialog.close();dialog.deleteLater()
        finally:
            theme.set_preference('dark')
            panel.deleteLater();editor.deleteLater();self.app.processEvents()


if __name__ == '__main__':
    unittest.main()
