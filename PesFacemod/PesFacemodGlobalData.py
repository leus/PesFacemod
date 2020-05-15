import os
import re


class PesFacemodGlobalData:
    p = re.compile(r'(.*)\\(\d+)\\#Win\\face\.fpk')
    facepath = ''
    vertexgroup_disable = False
    base_path = ''
    player_id = 0

    face_fpk = ''
    face_fmdl = ''
    hair_fmdl = ''
    oral_fmdl = ''

    eye_occlusion_alp = ''
    face_bsm_alp = ''
    face_nrm = ''
    face_srm = ''
    face_trm = ''
    hair_parts_bsm_alp = ''
    hair_parts_nrm = ''
    hair_parts_srm = ''
    hair_parts_trm = ''
    diff_bin = ''

    @classmethod
    def fpk_path(cls, *file):
        return os.path.join(cls.base_path, str(cls.player_id), '#Win', *file)

    @classmethod
    def tex_path(cls, *file):
        return os.path.join(cls.base_path, str(cls.player_id), 'sourceimages', '#windx11', *file)

    @classmethod
    def load(cls, path):
        cls.facepath = path
        m = cls.p.match(path)
        if m and os.path.isfile(cls.facepath):
            # (path, filename) = os.path.split(cls.facepath)
            # obtain all relevants path parts and files for the model
            # XXXXX\#Win\face.fpk
            cls.base_path = m.group(1)
            cls.player_id = m.group(2)
            cls.face_fpk = cls.fpk_path('face.fpk')
            cls.face_fmdl = cls.fpk_path('face_fpk', 'face_high.fmdl')
            cls.hair_fmdl = cls.fpk_path('face_fpk', 'hair_high.fmdl')
            cls.oral_fmdl = cls.fpk_path('face_fpk', 'oral_high.fmdl')
            cls.diff_bin = cls.fpk_path('face_fpk', 'face_diff.bin')

            # textures - without extension
            cls.eye_occlusion_alp = cls.tex_path('eye_occlusion_alp')
            cls.face_bsm_alp = cls.tex_path('face_bsm_alp')
            cls.face_nrm = cls.tex_path('face_nrm')
            cls.face_srm = cls.tex_path('face_srm')
            cls.face_trm = cls.tex_path('face_trm')
            cls.hair_parts_bsm_alp = cls.tex_path('hair_parts_bsm_alp')
            cls.hair_parts_nrm = cls.tex_path('hair_parts_nrm')
            cls.hair_parts_srm = cls.tex_path('hair_parts_srm')
            cls.hair_parts_trm = cls.tex_path('hair_parts_trm')

    @classmethod
    def good_path(cls, path):
        return cls.p.match(path) and os.path.isfile(PesFacemodGlobalData.facepath)

    @classmethod
    def clear(cls):
        cls.facepath = ''
        cls.vertexgroup_disable = False
        cls.base_path = ''
        cls.player_id = 0
        cls.face_fpk = ''
        cls.face_fmdl = ''
        cls.hair_fmdl = ''
        cls.oral_fmdl = ''
        cls.eye_occlusion_alp = ''
        cls.face_bsm_alp = ''
        cls.face_nrm = ''
        cls.face_srm = ''
        cls.face_trm = ''
        cls.hair_parts_bsm_alp = ''
        cls.hair_parts_nrm = ''
        cls.hair_parts_srm = ''
        cls.hair_parts_trm = ''
        cls.diff_bin = ''
