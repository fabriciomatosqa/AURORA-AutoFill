"""Convert the supplied feedback recording to the app's portable PCM WAV asset.

Usage: python tools/import_feedback.py path/to/recording.mp3
Qt Multimedia is needed only for this asset preparation, never at runtime.
"""
import argparse
from pathlib import Path
import wave

from PySide6.QtCore import QCoreApplication, QUrl, QTimer
from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'assets/command_click.wav')
    args = parser.parse_args()
    app = QCoreApplication([])
    decoder = QAudioDecoder()
    audio_format = QAudioFormat()
    audio_format.setSampleRate(44100)
    audio_format.setChannelCount(1)
    audio_format.setSampleFormat(QAudioFormat.Int16)
    decoder.setAudioFormat(audio_format)
    decoder.setSource(QUrl.fromLocalFile(str(args.source.resolve())))
    chunks, errors = [], []
    decoder.bufferReady.connect(lambda: chunks.append(bytes(decoder.read().data())))
    decoder.finished.connect(app.quit)
    def fail(*_):
        errors.append(decoder.errorString() or 'Audio decoding timed out')
        app.quit()
    decoder.error.connect(fail)
    QTimer.singleShot(15000, fail)
    decoder.start()
    app.exec()
    if errors or not chunks:
        raise RuntimeError('; '.join(errors) or 'No audio decoded')
    with wave.open(str(args.output), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(44100)
        output.writeframes(b''.join(chunks))
    print(f'Converted {sum(map(len, chunks)) // 2} samples to {args.output.name}')


if __name__ == '__main__':
    main()
