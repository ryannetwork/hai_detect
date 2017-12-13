"""
This module defines classes that are used to represent texts and annotations.
"""
import os

from nltk.tokenize import WhitespaceTokenizer

import xml.etree.ElementTree as ElementTree
from xml.etree.ElementTree import Element, SubElement

from annotations.Annotation import Annotation
from models.mention_level_models import MentionLevelModel


class ClinicalTextDocument(object):
    """
    This class is a representation of a single clinical documents.
    It is initialized either with `text`, an unprocessed text document
    and `rpt_id`, a unique identifier for the file (most often the filename),
    OR `filepath`, a filepath to a single report.
    In order to preserve the initial document spans,
    this is saved as an attribute `raw_text`.
    """

    def __init__(self, text=None, rpt_id='', filepath=None):
        if (not text) and filepath:
            text = self.from_filepath(filepath)
            rpt_id = os.path.splitext(os.path.basename(filepath))[0]

        self.raw_text = text
        self.rpt_id = rpt_id
        self.original_spans = self.get_text_spans(text)
        self.preprocessed_text = self.preprocess(text)
        self.split_text_and_spans = None
        self.sentences = [] # This will be a list of dictionairies
                            # where each dict contains {
                            # 'idx': int, 'text': sentence, 'word_spans': [(start, end), ...], 'span': (start, end)
                            # }
        self.annotations = []
        self.sentences_with_annotations = []
        self.element_tree = None

        # Split into sentences
        # While maintaining the original text spans
        self.sentences = self.split_sentences(self.preprocessed_text, self.original_spans)


    def from_filepath(self, filepath):
        with open(filepath) as f:
            text = f.read()
        return text


    def get_text_spans(self, text):
        """
        Returns a list of two-tuples consisitng of (`word`, (`start`, `end`))
        for each word in `text`.
        The tokens are tokenized only by whitespaces
        :param text: [str]
        :return: a list of two-tuples representing individual tokens and their spans
        """
        span_generator = WhitespaceTokenizer().span_tokenize(text)
        return list(span_generator)


    def preprocess(self, text):
        """
        Returns preprocessed text.
        Currently only lower-cased
        """
        # Split by white space
        text = text.lower()
        words = text.split()

        # Do preprocessing by removing replacing tokens with empty strings
        # or changing tokens.
        # The original spans will be maintained

        text = ' '.join(words)
        return text


    def split_sentences(self, text, spans):
        """
        Iterates through tokens in text.split().
        At each termination point, a new sentence is started
        unless that token is part of the exception words.
        :return:
            `sentences`: a list of lists of words split by whitespace
                - [['this', 'is', 'a', 'sentence'],
                  ['and', 'this', 'is', 'another.']]
            `word_spans`: a list lists of two-tuples representing word start and end points
                - [[(0, 4), (5, 7), (8, 9), (10, 19)],
                  [(20, 23), (24, 28), (29, 31), (32, 40)]]
            `sentence_spans`: a list of start and end point for sentences
                - [(0, 19), (20, 40)])
            list of sentences and spans
        """

        termination_points = '.!?'
        exception_words = ['dr.', 'm.d', 'mr.', 'ms.', 'mrs.', ]

        words = text.split()

        sentences = [] # List of list of words
        #word_spans = [] # List of list of start, end points for words
        #sentence_spans = [] # List of start, end points for sentences

        idx = 0
        sentence_dict = {}
        current_sentence = []
        current_spans = []
        for word, span in zip(words, spans):
            # Populate `current_sentence` with words
            # and `current_spans` with spans for each word
            current_sentence.append(word)
            current_spans.append(span)

            if word[-1] in termination_points and word not in exception_words:
                # Add `current_sentence` and `current_spans` to larger lists
                sentence_dict['text'] = ' '.join(current_sentence)
                sentence_dict['words'] = current_sentence
                sentence_dict['idx'] = idx
                sentence_dict['span'] = (current_spans[0][0], current_spans[-1][-1])
                sentence_dict['word_spans'] = current_spans
                sentences.append(sentence_dict)

                # Start a new sentence
                idx += 1
                sentence_dict = {}
                current_sentence = []
                current_spans = []

        # Take care of any words remaining
        if len(current_sentence):
            sentence_dict['text'] = ' '.join(current_sentence)
            sentence_dict['words'] = current_sentence
            sentence_dict['idx'] = idx
            sentence_dict['span'] = (current_spans[0][0], current_spans[-1][-1])
            sentence_dict['word_spans'] = current_spans
            sentences.append(sentence_dict)

        return sentences

    def annotate(self, model):
        """
        This methods takes a MentionLevelModel that identifies targets and modifiers.
        For each sentence in self.sentences, the model identifies all findings using pyConText.
        These markups are then used to create Annotations and are added to `sentence['annotations']`
        """
        for sentence_num, sentence in enumerate(self.sentences):
            markup = model.markup_sentence(sentence['text'])
            targets = markup.getMarkedTargets()

            # Create annotations out of targets
            for target in targets:
                annotation = Annotation()
                annotation.from_markup(target, markup, sentence['text'], sentence['span'])
                annotation.sentence_num = sentence_num
                # TODO: decide whether to exclude annotations without anatomy
                self.sentences_with_annotations.append(sentence_num)
                self.annotations.append(annotation)


    def get_annotations(self):
        """
        Returns a list of annotations.
        """
        return self.annotations


    def to_etree(self):
        """
        Creates an eTree XML element
        """
        root = Element('annotations')
        root.set('textSource', self.rpt_id + '.txt')
        # TODO:
        for annotation in self.annotations:
            annotation_body, mention_class = annotation.to_etree()
            root.append(annotation_body)
            root.append(mention_class)
            #root.append(annotation.to_etree())
            #root.append(annotation.get_xml())
            #root.append(annotation.get_mention_xml())

        # xml for adjudication status
        adjudication_status = SubElement(root, 'eHOST_Adjudication_status')
        adjudication_status.set('version','1.0')
        selected_annotators = SubElement(adjudication_status,'Adjudication_Selected_Annotators')
        selected_annotators.set('version','1.0')
        selected_classes = SubElement(adjudication_status,'Adjudication_Selected_Classes')
        selected_classes.set('version','1.0')
        adjudication_others = SubElement(adjudication_status,'Adjudication_Others')

        check_spans = SubElement(adjudication_others,'CHECK_OVERLAPPED_SPANS')
        check_spans.text = 'false'
        check_attributes = SubElement(adjudication_others,'CHECK_ATTRIBUTES')
        check_attributes.text = 'false'
        check_relationship = SubElement(adjudication_others,'CHECK_RELATIONSHIP')
        check_relationship.text = 'false'
        check_class = SubElement(adjudication_others,'CHECK_CLASS')
        check_class.text = 'false'
        check_comment = SubElement(adjudication_others,'CHECK_COMMENT')
        check_comment.text = 'false'

        return ElementTree.ElementTree(root)


        #self.element_tree = ElementTree.ElementTree(root)



    def to_knowtator(self, outdir):
        """
        This method saves all annotations in an instance of ClinicalTextDocument to a .knowtator.xml file
        to be imported into eHOST.
        outdir is the directory to which the document will be saved.
        The outpath will be '/path/to/outdir/rpt_id.knowtator.xml'
        """
        if not os.path.isdir(outdir):
            raise FileNotFoundError("{} is not a directory".format(outdir))
        outpath = os.path.join(outdir, self.rpt_id + '.txt.knowtator.xml')
        element_tree = self.to_etree()
        f_out = open(outpath, 'w')
        element_tree.write(f_out, encoding='unicode')
        print("Saved at {}".format(outpath))
        f_out.close()




    def __str__(self):
        string = ''
        string += 'Report: {0}\n'.format(self.rpt_id)
        for sentence_num, sentence in enumerate(self.sentences):
            string += '{text} '.format(**sentence)
            if sentence_num in self.sentences_with_annotations:
                for annotation in [a for a in self.annotations if a.sentence_num == sentence_num]:
                    string +=  annotation.get_short_string() + '\n'
        return string


def main():
    """
    An example of processing one text document.
    """

    # Create a model with modifiers and targets
    targets = os.path.abspath('../lexicon/targets.tsv')
    modifiers = os.path.abspath('../lexicon/modifiers.tsv')
    model = MentionLevelModel(targets, modifiers)

    text = "We examined the patient yesterday. He shows signs of pneumonia.\
    The wound is CDI. He has not developed a urinary tract infection\
    However, there is a wound infection near the abdomen. There is no surgical site infection.\
    There is an abscess. Signed, Dr.Doctor MD."
    rpt_id = 'example_report'
    document = ClinicalTextDocument(text, rpt_id='example_report')
    document.annotate(model)
    print(document)

    outdir = 'tmp'
    document.to_knowtator(outdir)
    exit()

    for annotation in document.annotations:
        print(annotation)
        print(annotation.to_etree())
        print()


if __name__ == '__main__':
    main()
    exit()


