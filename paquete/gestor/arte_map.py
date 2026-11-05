"""Dónde vive el arte y el vídeo en la carpeta ARTE (y cómo volver al «dueño» lógico de cada archivo).

ARTE\\
  Álbumes\\<álbum>\\Portadas y arte | Vídeo y clips | Proyectos de vídeo
  Álbumes\\<álbum>\\<NN canción>\\Arte | Vídeo
  Singles\\<título>\\Arte | Vídeo
  Pre-released\\<título>\\Arte | Vídeo
  Proyectos\\<proyecto>\\Portadas y arte | Vídeo y clips | Proyectos de vídeo
  Proyectos\\<proyecto>\\<canción>\\Arte | Vídeo
  Sin publicar\\<canción>\\Arte | Vídeo

El «dueño lógico» es la carpeta de la canción o del álbum en published / prereleased / unreleased
(p. ej. published/Álbumes/Mi álbum/01 Mi canción): así el gestor sigue sabiendo a quién pertenece.
"""
ALB = {"arte": "Portadas y arte", "video": "Vídeo y clips", "proyectos": "Proyectos de vídeo"}
SONG = {"arte": "Arte", "video": "Vídeo"}
ALB_MARK = set(ALB.values())
SONG_MARK = set(SONG.values())
ALBUMES = "Álbumes"


def norm_albumes(x):
    return x.lower().replace("á", "a") == "albumes"


def base_for(parts, projects=()):
    """parts: carpeta lógica de la canción/álbum (['published','Álbumes','A','01 T']). Devuelve la ruta bajo ARTE o None."""
    p = list(parts)
    if not p:
        return None
    if p[0] == "published" and len(p) >= 3 and norm_albumes(p[1]):
        return [ALBUMES] + p[2:]
    if p[0] == "published" and len(p) == 3 and p[1] == "Singles":
        return ["Singles", p[2]]
    if p[0] == "prereleased" and len(p) == 2:
        return ["Pre-released", p[1]]
    if p[0] == "unreleased":
        if len(p) == 2:
            return ["Proyectos", p[1]] if p[1] in projects else ["Sin publicar", p[1]]
        if len(p) == 3:
            return ["Proyectos", p[1], p[2]]
    return None


def owner_of(arte_parts):
    """arte_parts: ruta bajo ARTE. Devuelve (partes del dueño lógico, 'album'|'cancion', 'arte'|'video'|'proyectos') o None."""
    p = list(arte_parts)
    if len(p) < 3:
        return None
    g = p[0]
    if g in (ALBUMES, "Proyectos"):
        top = ["published", "Álbumes", p[1]] if g == ALBUMES else ["unreleased", p[1]]
        if p[2] in ALB_MARK:
            return top, "album", p[2]
        if len(p) >= 4 and p[3] in SONG_MARK:
            return top + [p[2]], "cancion", p[3]
        return None
    if g in ("Singles", "Pre-released", "Sin publicar") and p[2] in SONG_MARK:
        owner = {"Singles": ["published", "Singles", p[1]], "Pre-released": ["prereleased", p[1]], "Sin publicar": ["unreleased", p[1]]}[g]
        return owner, "cancion", p[2]
    return None


def is_album_owner(parts, projects=()):
    """¿La carpeta lógica es un álbum/proyecto (no una canción)?"""
    p = list(parts)
    return (p[0] == "published" and len(p) == 3 and norm_albumes(p[1])) or (p[0] == "unreleased" and len(p) == 2 and p[1] in projects)
