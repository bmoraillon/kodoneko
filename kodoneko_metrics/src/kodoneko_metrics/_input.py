"""
Normalisation des entrées polymorphes (str, bytes, PathLike, IO).

Auteur : Benoît Moraillon
Licence : AGPL-3.0
"""
from __future__ import annotations

import os
from typing import IO, Optional, Union

SourceInput = Union[str, bytes, os.PathLike, IO]


def normalize_input(
    source: SourceInput,
    *,
    encoding: str = "utf-8",
    treat_str_as: str = "auto",
) -> tuple[str, Optional[str]]:
    """Convertit une source polymorphe en (text, hint_path).

    Paramètres
    ----------
    source : str | bytes | PathLike | IO
        L'entrée à normaliser.
    encoding : str
        Encodage utilisé pour décoder les bytes et lire les fichiers.
    treat_str_as : {"auto", "code", "path"}
        - "auto" : si la chaîne contient un saut de ligne ou dépasse
          4096 caractères, elle est traitée comme du code source.
          Sinon, on tente de l'ouvrir comme un chemin ; fallback en code.
        - "code" : force l'interprétation comme code source.
        - "path" : force l'interprétation comme chemin de fichier.

    Retourne
    --------
    (text, hint_path) où hint_path est le chemin du fichier d'origine
    si on en a un (utile pour la détection par extension).
    """
    if isinstance(source, os.PathLike):
        path = os.fspath(source)
        with open(path, "r", encoding=encoding) as f:
            return f.read(), path

    if isinstance(source, (bytes, bytearray)):
        return bytes(source).decode(encoding), None

    if isinstance(source, str):
        if treat_str_as == "code":
            return source, None
        if treat_str_as == "path":
            with open(source, "r", encoding=encoding) as f:
                return f.read(), source
        # auto
        looks_like_code = ("\n" in source) or (len(source) > 4096)
        if looks_like_code:
            return source, None
        try:
            if os.path.isfile(source):
                with open(source, "r", encoding=encoding) as f:
                    return f.read(), source
        except (OSError, ValueError):
            pass
        return source, None

    if hasattr(source, "read"):
        data = source.read()
        if isinstance(data, bytes):
            data = data.decode(encoding)
        hint = getattr(source, "name", None)
        if hint is not None and not isinstance(hint, str):
            hint = None
        if hint and (hint.startswith("<") or hint.startswith("/dev/")):
            hint = None
        return data, hint

    raise TypeError(
        f"Type de source non pris en charge : {type(source).__name__}. "
        f"Attendu : str, bytes, PathLike, ou IO (.read())."
    )
