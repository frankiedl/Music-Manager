"""Where artwork and video live inside the ARTE folder (and how to get back to the logical "owner" of each file).

ARTE\\
  Álbumes\\<album>\\Portadas y arte | Vídeo y clips | Proyectos de vídeo
  Álbumes\\<album>\\<NN song>\\Arte | Vídeo
  Singles\\<title>\\Arte | Vídeo
  Pre-released\\<title>\\Arte | Vídeo
  Proyectos\\<project>\\Portadas y arte | Vídeo y clips | Proyectos de vídeo
  Proyectos\\<project>\\<song>\\Arte | Vídeo
  Sin publicar\\<song>\\Arte | Vídeo

The "logical owner" is the song or album folder in published / prereleased / unreleased
(e.g. published/Álbumes/My album/01 My song): this way the manager still knows who each file belongs to.
(Folder names above are the real, Spanish, on-disk names: they are part of the library layout.)
"""
ALB = {"arte": "Portadas y arte", "video": "Vídeo y clips", "proyectos": "Proyectos de vídeo"}
SONG = {"arte": "Arte", "video": "Vídeo"}
ALB_MARK = set(ALB.values())
SONG_MARK = set(SONG.values())
ALBUMES = "Álbumes"


def norm_albumes(x):
    return x.lower().replace("á", "a") == "albumes"


def base_for(parts, projects=()):
    """parts: logical folder of the song/album (['published','Álbumes','A','01 T']). Returns the path under ARTE or None."""
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
    """arte_parts: path under ARTE. Returns (logical owner parts, 'album'|'cancion', 'arte'|'video'|'proyectos') or None."""
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
    """Is the logical folder an album/project (not a song)?"""
    p = list(parts)
    return (p[0] == "published" and len(p) == 3 and norm_albumes(p[1])) or (p[0] == "unreleased" and len(p) == 2 and p[1] in projects)
