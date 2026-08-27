from infraestructura import repositorio_historial as history_repository


def save(filename: str, backend: str, text_content: str, srt_content: str):
    history_repository.save_transcription(filename, backend, text_content, srt_content)


def list_all():
    return history_repository.get_all_transcriptions()
