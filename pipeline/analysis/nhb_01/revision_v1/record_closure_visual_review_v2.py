"""Record the assistant's actual image inspection, not automatic scientific certification."""
from datetime import datetime, timezone
from local_recall import MODULE, require, sha, write_json
SOURCE=MODULE/'figure1_revision_final_v2'
OUT=MODULE/'closure_visual_review_v2'

def main():
    previews=[OUT/f'{name}-{n}.png' for name in
        ['supplement_raw_domestic_all_countries','supplement_paired_domestic_all_countries'] for n in range(1,6)]
    require(all(p.is_file() for p in previews),'All ten rendered pages required')
    write_json(OUT/'visual_review_record.json',{
        'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'reviewer':'current_assistant',
        'source_manifest_sha256':sha(SOURCE/'run_manifest.json'),
        'assistant_visual_review_completed':True,'human_author_review':'pending',
        'reviewed_figures':['figure1_revised_a_d.png','supplement_annual_country_diffusion.png',
            'supplement_gini_full_axis.png','cached_supplement_first_observed_map.png'],
        'reviewed_pdf_pages':{'raw_domestic_heatmap':5,'paired_domestic_heatmap':5},
        'observations':['Main labels, counts, axes and fixed country legend are visible; shared zoom keeps the same ranges.',
            'Unknown credit is hatched and missing heatmap denominators are grey, distinct from zero.',
            'All ten heatmap pages have unclipped titles, country codes, year ticks and common within-bundle color scales.',
            'Complete 0–1 Gini view agrees with the main truncated-axis view.',
            'Map silhouette and caption fit; 142 located codes of 143, RE remains unlocated and included in tables.'],
        'remaining_presentation_limits':['Dense scatter clouds should be read together with exact CSVs.',
            'Small fonts and reduced journal-layout sizes require final author/venue-specific review.',
            'No claim of complete color-vision accessibility, publisher compliance or independent semantic gold.'],
        'preview_hashes':{p.name:sha(p) for p in previews},
        'scientific_validity_certified_by_visuals':False,'submission_ready':False,'paid_api_calls':0})
    print('Actual bounded assistant visual inspection recorded; author/venue review remains separate.')

if __name__=='__main__':main()
