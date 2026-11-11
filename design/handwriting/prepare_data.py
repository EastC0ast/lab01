"""Prepare auditable measurements of UCI UJIpenchars2 lowercase Latin 'a'.

Uses only the Python standard library. The source ZIP is preserved byte-for-byte;
coordinates and stroke boundaries are read without smoothing or deduplication.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import fmean
from urllib.request import Request, urlopen
import zipfile


HERE = Path(__file__).resolve().parent
DATA = HERE / 'data'
SOURCE_URL = 'https://archive.ics.uci.edu/static/public/177/uji+pen+characters+version+2.zip'
SOURCE_SHA256 = '0881b522911b99d9922820289441b50fd3d307f71cd7f9cc70e86872424a5f90'
DATASET_URL = 'https://archive.ics.uci.edu/dataset/177/uji+pen+characters+version+2'
METADATA_URL = 'https://archive.ics.uci.edu/api/dataset?id=177'
DOI = '10.24432/C5FG8S'
ARCHIVE = DATA / 'uji_pen_characters_version2.zip'
CHARACTER = 'a'  # Chosen before inspecting the measurements or testing a correlation.
SITE_UNITS_PER_MM = {'UJI': 100, 'UPV': 152}
GLYPH_FIELDS = [
    'sample_id', 'character', 'writer_id', 'writer_number', 'split', 'site',
    'repetition', 'ink_units_per_mm', 'n_strokes', 'n_points',
    'x_min_ink', 'x_max_ink', 'y_min_ink', 'y_max_ink',
    'width_ink', 'height_ink', 'width_mm', 'height_mm',
]
WRITER_FIELDS = [
    'writer_id', 'writer_number', 'split', 'site', 'ink_units_per_mm',
    'n_samples', 'width_mean_ink', 'height_mean_ink',
    'width_mean_mm', 'height_mean_mm',
]


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def bounding_box(strokes):
    """Return the extrema and max-minus-min extents over all raw stroke points."""
    if not strokes or any(not stroke for stroke in strokes):
        raise ValueError('A sample must contain non-empty strokes.')
    points = [point for stroke in strokes for point in stroke]
    if any(len(point) != 2 for point in points):
        raise ValueError('Each point must contain exactly X and Y.')
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    x_min, x_max, y_min, y_max = min(xs), max(xs), min(ys), max(ys)
    return {
        'n_strokes': len(strokes), 'n_points': len(points),
        'x_min_ink': x_min, 'x_max_ink': x_max,
        'y_min_ink': y_min, 'y_max_ink': y_max,
        'width_ink': x_max - x_min, 'height_ink': y_max - y_min,
    }


def parse_ujipenchars(text: str):
    """Parse Version 2 WORD/NUMSTROKES/POINTS text; return records with strokes.

    Negative coordinates and consecutive identical points are retained. This is
    the documented Version 2 format, not the UNIPEN .SEGMENT/.PEN_DOWN format.
    """
    lines = []
    declared_scales = {}
    for line_number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith('//'):
            scale = re.fullmatch(r'//\s*(UJI|UPV):\s*(\d+) units per millimetre', stripped)
            if scale:
                site, value = scale.group(1), int(scale.group(2))
                if value != SITE_UNITS_PER_MM[site]:
                    raise ValueError(f'Unexpected coordinate scale at line {line_number}.')
                declared_scales[site] = value
            continue
        if stripped:
            lines.append((line_number, stripped))

    records = []
    index = 0
    while index < len(lines):
        line_number, line = lines[index]
        header = re.fullmatch(r'WORD\s+(\S)\s+((trn|tst)_(UJI|UPV)_W(\d{2})-(\d{2}))', line)
        if not header:
            raise ValueError(f'Invalid WORD header at line {line_number}: {line!r}')
        character, session_id, split, site, writer_number, repetition = header.groups()
        index += 1
        if index >= len(lines):
            raise ValueError('Truncated sample: missing NUMSTROKES.')
        count_line_number, count_line = lines[index]
        count_match = re.fullmatch(r'NUMSTROKES\s+(\d+)', count_line)
        if not count_match or int(count_match.group(1)) < 1:
            raise ValueError(f'Invalid NUMSTROKES at line {count_line_number}.')
        n_strokes = int(count_match.group(1))
        index += 1
        strokes = []
        for _ in range(n_strokes):
            if index >= len(lines):
                raise ValueError('Truncated sample: missing POINTS.')
            point_line_number, point_line = lines[index]
            point_match = re.fullmatch(r'POINTS\s+(\d+)\s+#\s+(.+)', point_line)
            if not point_match:
                raise ValueError(f'Invalid POINTS at line {point_line_number}.')
            n_points = int(point_match.group(1))
            try:
                coordinates = [int(value) for value in point_match.group(2).split()]
            except ValueError as exc:
                raise ValueError(f'Non-integer coordinate at line {point_line_number}.') from exc
            if n_points < 1 or len(coordinates) != 2 * n_points:
                raise ValueError(f'POINTS count mismatch at line {point_line_number}.')
            strokes.append(list(zip(coordinates[::2], coordinates[1::2])))
            index += 1
        bbox = bounding_box(strokes)
        scale = SITE_UNITS_PER_MM[site]
        records.append({
            'sample_id': f'{session_id}-U+{ord(character):04X}',
            'character': character, 'writer_id': session_id.rsplit('-', 1)[0],
            'writer_number': int(writer_number), 'split': split, 'site': site,
            'repetition': int(repetition), 'ink_units_per_mm': scale,
            **bbox,
            'width_mm': bbox['width_ink'] / scale,
            'height_mm': bbox['height_ink'] / scale,
            'strokes': strokes,
        })
    if len({record['sample_id'] for record in records}) != len(records):
        raise ValueError('Duplicate character/session sample in the source.')
    return records


def parse_archive(path=ARCHIVE):
    """Read the original ZIP and return all records, including raw XY strokes."""
    with zipfile.ZipFile(path) as archive:
        return parse_ujipenchars(archive.read('ujipenchars2.txt').decode('utf-8'))


def aggregate_writer_means(records):
    """Average paired repetitions within each writer; retain raw and screen mm."""
    groups = defaultdict(list)
    for record in records:
        groups[record['writer_id']].append(record)
    results = []
    metadata_fields = ['writer_number', 'split', 'site', 'ink_units_per_mm']
    for writer_id, group in sorted(groups.items()):
        first = group[0]
        if any(any(record[key] != first[key] for key in metadata_fields) for record in group):
            raise ValueError(f'Inconsistent writer metadata: {writer_id}')
        repetitions = [record['repetition'] for record in group]
        if len(set(repetitions)) != len(repetitions):
            raise ValueError(f'Duplicate repetition for writer: {writer_id}')
        scale = first['ink_units_per_mm']
        if not isinstance(scale, (int, float)) or not math.isfinite(scale) or scale <= 0:
            raise ValueError(f'Invalid coordinate scale: {writer_id}')
        for record in group:
            for dimension in ['width', 'height']:
                expected = record[f'{dimension}_ink'] / scale
                if f'{dimension}_mm' in record and not math.isclose(record[f'{dimension}_mm'], expected, rel_tol=1e-12, abs_tol=1e-12):
                    raise ValueError(f'Inconsistent conversion to screen mm: {writer_id}')
        width_mean_ink = fmean(record['width_ink'] for record in group)
        height_mean_ink = fmean(record['height_ink'] for record in group)
        results.append({
            'writer_id': writer_id,
            **{key: first[key] for key in metadata_fields},
            'n_samples': len(group),
            'width_mean_ink': width_mean_ink,
            'height_mean_ink': height_mean_ink,
            'width_mean_mm': width_mean_ink / scale,
            'height_mean_mm': height_mean_ink / scale,
        })
    return results


def validate_selection(records, expected_writers=60, repetitions=(1, 2)):
    """Require the prespecified character, complete paired sessions, no dropping."""
    if not records or {record['character'] for record in records} != {CHARACTER}:
        raise ValueError('Selection must contain exactly lowercase Latin a (U+0061).')
    groups = defaultdict(list)
    for record in records:
        groups[record['writer_id']].append(record)
        for dimension in ['width', 'height']:
            if record[f'{dimension}_ink'] <= 0:
                raise ValueError(f'Non-positive extent requires review: {record["sample_id"]}')
    if len(groups) != expected_writers:
        raise ValueError(f'Expected {expected_writers} writers, got {len(groups)}.')
    for writer_id, group in groups.items():
        if sorted(record['repetition'] for record in group) != sorted(repetitions):
            raise ValueError(f'Expected repetitions {repetitions} for {writer_id}.')
    means = aggregate_writer_means(records)
    return {
        'character': CHARACTER,
        'n_glyphs': len(records), 'n_writers': len(groups),
        'repetitions': list(repetitions),
        'writers_by_site': dict(sorted(Counter(record['site'] for record in means).items())),
        'glyphs_by_site': dict(sorted(Counter(record['site'] for record in records).items())),
        'dropped_glyphs': 0,
    }


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def write_csv(path: Path, records, fields):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore', lineterminator='\n')
        writer.writeheader()
        writer.writerows(records)


def download(url: str) -> bytes:
    request = Request(url, headers={'User-Agent': 'Lab01 reproducibility research'})
    with urlopen(request, timeout=60) as response:
        return response.read()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true', help='Obtain missing source ZIP and official API metadata.')
    args = parser.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    plan_path = DATA / 'selection_plan.json'
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    if plan['character'] != CHARACTER or plan['primary_units'] != 'screen millimetres':
        raise ValueError('Selection plan does not match this analysis.')
    if args.download and not ARCHIVE.exists():
        raw = download(SOURCE_URL)
        if sha256(raw) != SOURCE_SHA256:
            raise ValueError('Official source ZIP changed; review before proceeding.')
        ARCHIVE.write_bytes(raw)
    if not ARCHIVE.exists():
        raise FileNotFoundError('Source ZIP is missing; rerun with --download.')
    archive_bytes = ARCHIVE.read_bytes()
    if sha256(archive_bytes) != SOURCE_SHA256:
        raise ValueError('Source ZIP checksum mismatch; refusing to process changed data.')
    api_path = DATA / 'uci_metadata.json'
    if args.download and not api_path.exists():
        api_raw = download(METADATA_URL)
        json.loads(api_raw)
        api_path.write_bytes(api_raw)

    records = parse_archive(ARCHIVE)
    if len(records) != 11640 or len({record['character'] for record in records}) != 97:
        raise ValueError('Expected 11640 samples and 97 characters in Version 2.')
    writer_numbers = {record['writer_number'] for record in records}
    if writer_numbers != set(range(1, 61)):
        raise ValueError('Expected exactly writer numbers 1 through 60.')
    if any(count != 194 for count in Counter(record['writer_id'] for record in records).values()):
        raise ValueError('Expected 97 characters times two repetitions for every writer.')
    selected = [record for record in records if record['character'] == CHARACTER]
    verification = validate_selection(selected)
    means = aggregate_writer_means(selected)
    write_csv(DATA / 'glyphs.csv', selected, GLYPH_FIELDS)
    write_csv(DATA / 'writer_means.csv', means, WRITER_FIELDS)
    write_json(DATA / 'samples.json', selected)
    with zipfile.ZipFile(ARCHIVE) as archive:
        members = {name: {'bytes': len(archive.read(name)), 'sha256': sha256(archive.read(name))} for name in archive.namelist()}
        # Keep original metadata bytes and CRLF endings; uji2.names uses Latin-1.
        (DATA / 'uji2.names').write_bytes(archive.read('uji2.names'))
    provenance = {
        'dataset': 'UJI Pen Characters (Version 2)', 'uci_id': 177,
        'dataset_url': DATASET_URL, 'doi': DOI,
        'citation': 'Prat, F., Castro, M., Llorens, D., Marzal, A., & Vilar, J. (2008). UJI Pen Characters (Version 2) [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5FG8S.',
        'license': 'CC BY 4.0',
        'license_url': 'https://creativecommons.org/licenses/by/4.0/',
        'license_information_source': DATASET_URL,
        'retrieved_date': '2026-11-11',
        'source_zip': {'path': ARCHIVE.name, 'url': SOURCE_URL, 'bytes': len(archive_bytes), 'sha256': SOURCE_SHA256},
        'source_members': members,
        'source_format': 'Version 2 WORD / NUMSTROKES / POINTS n # x y ...; sample file UTF-8; uji2.names Latin-1.',
        'selection_plan': plan,
        'complete_dataset': {'n_glyphs': len(records), 'n_characters': 97, 'n_writers': 60, 'samples_per_writer': 194},
        'selected_dataset': verification,
        'derived_quantities': {
            'width_ink': 'max(X)-min(X), over all points of all strokes; no +1',
            'height_ink': 'max(Y)-min(Y), over all points of all strokes; no +1',
            'width_mm': 'width_ink / ink_units_per_mm',
            'height_mm': 'height_ink / ink_units_per_mm',
            'ink_units_per_mm': SITE_UNITS_PER_MM,
            'physical_interpretation': 'Screen-coordinate millimetres using site calibration in uji2.names; not measurements on paper.',
            'x_axis': 'Increases left to right', 'y_axis': 'Increases top to bottom',
        },
        'preprocessing': {
            'smoothing': False, 'deduplication': False, 'rotation': False,
            'shape_normalization': False, 'outlier_removal': False,
            'box_clipping': False, 'negative_coordinates_preserved': True,
            'missing_or_nonpositive_selected_extents': 0,
            'unselected_characters': '11520 glyphs excluded solely because character != a, as prespecified.',
        },
        'dependence_analysis_unit': '60 paired writer means in screen millimetres; each writer contributes one pair based on both repetitions.',
        'site_caveat': 'UJI and UPV use different coordinate scales (100 and 152 ink units/mm). Pooling unconverted ink extents would introduce a site scale confound. Screen-mm conversion corrects this documented scale, but site and population differences remain for sensitivity analysis.',
        'limitations': [
            'Characters were written in guided acquisition boxes on a tablet, not free writing on paper.',
            'The 60 writers are not documented as a random sample of a general population.',
            'Two repeated sessions per writer are not treated as independent writers.',
            'Only XY coordinates were recorded: no time or pressure information exists.',
        ],
        'generated_files': {
            name: {'sha256': sha256((DATA / name).read_bytes()), 'bytes': (DATA / name).stat().st_size}
            for name in ['glyphs.csv', 'writer_means.csv', 'samples.json']
        },
    }
    if api_path.exists():
        provenance['official_api_metadata'] = {'path': api_path.name, 'url': METADATA_URL, 'sha256': sha256(api_path.read_bytes())}
    write_json(DATA / 'provenance.json', provenance)
    print(json.dumps({'source_sha256': SOURCE_SHA256, 'complete_samples': len(records), **verification}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
