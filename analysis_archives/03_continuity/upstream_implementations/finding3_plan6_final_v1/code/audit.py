"""Numerical and technical release audit, with explicit scientific limits."""
from common import *
import re,urllib.parse,subprocess
from PIL import Image

def links(root):
    rows=[]
    for p in root.rglob('*.md'):
        for match in re.finditer(r'\]\(([^\n]*?)\)',p.read_text()):
            target=match.group(1).strip().strip('<>')
            if target.startswith(('https://','http://','mailto:','#')):continue
            path=urllib.parse.unquote(target.split('#')[0])
            if not path:continue
            q=(p.parent/path).resolve();require(q.is_relative_to(root.resolve()) and q.exists(),'Broken/nonportable link '+str(p)+' -> '+target)
            rows.append(dict(file=str(p.relative_to(root)),target=target))
    return rows

def numeric():
    checks={};x=load('entry_cohort');e=load('complete_cohort');r=load('repeat_cohort');a=load('Fig3a_entry_uses');b=load('Fig3b_repeat12');t=load('Fig3c_use_transitions');j=load('Fig3e_author_use')
    def check(name,ok):require(ok,name);checks[name]=True
    check('entry_cohort_6328',len(x)==6328 and x.institution_id.is_unique)
    check('complete_4955',len(e)==4955 and e.institution_id.is_unique and e.window_end.le(CUTOFF).all())
    check('confirmed_repeat_2137',len(r)==2137 and r.repeat_flag.fillna(False).all())
    check('repeat_unknown_307',e.repeat_flag.isna().sum()==307)
    check('strict_later_distinct_studies',r.followup_date.gt(r.entry_date).all() and r.followup_study_id.ne(r.entry_study_id).all())
    check('unchanged_baseline_groups',len(load('baseline_groups'))==52098)
    check('all_entry_groups_sum',x.size_group.value_counts().reindex(['L','M','H','Unclassified']).tolist()==[332,972,4695,329])
    check('initial_denominators',((a.Y+a.not_established).eq(a.D)&(a.D+a.unknown).eq(a.N)).all())
    check('repeat_denominators',(b.C+b.U+b.known_no_event).eq(b.N).all())
    check('registered_event_bounds',(b.upper.ge(b.fraction)&b.upper.le(1)).all())
    for name,frame in [('main',t),('author_joint',j),('sensitivity',load('S5_use_sensitivity'))]:
        check(name+'_four_cells',frame[['n00','n01','n10','n11']].sum(axis=1).eq(frame.N).all())
        nz=frame[frame.N.gt(0)]
        check(name+'_net_equals_marginal',np.allclose(nz.net_change_pp,100*(nz.followup_fraction-nz.entry_fraction),atol=1e-10))
        check(name+'_change_equals_opposite_directions',np.allclose(nz.change_rate,(nz.n01+nz.n10)/nz.N))
    author=load('Fig3d_author_groups').query('cohort=="All" and size_group=="All"')
    check('three_author_groups_1312',author.n.sum()==1312 and author.N.eq(1312).all() and set(author.author_group)==set(AUTH))
    check('main_category_pair_N',t.query('cohort=="All" and size_group=="All"').set_index('activity').loc[MODES].N.tolist()==[526,431,220,852])
    for file,table,keys,values in [
        ('repeat_12m_by_scale.csv','Fig3b_repeat12',['size_group'],{'eligible':'N','confirmed_repeat':'C','event_unknown':'U'}),
        ('entry_use_by_scale.csv','Fig3a_entry_uses',['size_group','activity'],{'entrants':'N','assessable':'D','supported':'Y'}),
        ('use_transitions_12m.csv','Fig3c_use_transitions',['activity'],{'N':'N','n00':'n00','n01':'n01','n10':'n10','n11':'n11'}),
        ('author_use_conditional_transitions_12m.csv','Fig3e_author_use',['activity','author_group'],{'N':'N','n00':'n00','n01':'n01','n10':'n10','n11':'n11'})]:
        expected=pd.read_csv(PLAN/'现有数据核对'/file);actual=load(table)
        if 'cohort' in actual:actual=actual[actual.cohort.eq('All')]
        if 'size_group' not in keys and 'size_group' in actual:actual=actual[actual.size_group.eq('All')]
        q=expected.merge(actual,on=keys,suffixes=('_expected','_actual'),validate='one_to_one')
        check('handoff_'+file,len(q)==len(expected) and all(np.allclose(q[k+'_expected'] if k in actual else q[k],q[v+'_actual'] if v in expected else q[v],equal_nan=True) for k,v in values.items()))
    w=load('standardization_weights')
    check('standardization_weights_sum1',np.allclose(w.groupby(['analysis','activity','context'],dropna=False).weight.sum(),1))
    s=load('standardized_estimates');raw=s[~s.analysis.eq('S7_equal_country')]
    check('no_support_no_extrapolation',raw.loc[raw.retained_N.eq(0),'fraction'].isna().all())
    check('supported_std_in_range',s.fraction.dropna().between(0,1).all())
    check('support_partition',(raw.retained_N+raw.excluded_N).eq(raw.original_N).all())
    context=load('ED6c_partner_context');check('partner_classes_partition',context.groupby(['cohort','size_group','activity','entry_state']).n.sum().eq(context.groupby(['cohort','size_group','activity','entry_state']).N.first()).all())
    rule=load('entry_partner_context');check('no_H_in_noH_class',rule.loc[rule.partner_class.eq('complete_no_H_partner'),'known_H_partners'].eq(0).all())
    check('single_requires_complete',rule.loc[rule.partner_class.eq('single_institution'),'observed_complete'].all())
    check('H_partner_requires_positive_link',rule.loc[rule.partner_class.eq('confirmed_H_partner'),'known_H_partners'].ge(1).all())
    win=load('S4_common_windows');win=win.query('cohort=="All"').pivot(index='size_group',columns='months',values='C');check('common_window_confirmation_monotone',(win[3].le(win[6])&win[6].le(win[12])).all())
    check('all_common_windows_same_N',load('S4_common_windows').query('cohort=="All" and size_group=="All"').N.eq(4955).all())
    blind=pd.read_csv(OUT/'validation_materials/blind_human_template.csv');check('human_labels_still_blank',len(blind)==960 and blind.human_state.isna().all())
    check('blind_contains_no_model_answers',not any('model' in v and v!='prior_model_answer_seen' for v in blind.columns))
    check('sample_work_unique',pd.read_csv(OUT/'validation_materials/sampling_registry.csv').work_id.nunique()==240)
    check('no_unvalidated_CIs',json.loads((OUT/'provenance/dependency12.json').read_text())['bootstrap_draws_executed']==0)
    check('ED7_record_ID_sets',load('ED7_development_record_audit').ID_set_check.eq('PASS').all())
    proxy=load('S2_reference_proxies');cross=load('S2_reference_action_crosscheck')
    check('reference_proxy_unique_work',proxy.work_id.is_unique and len(proxy)==23456)
    check('reference_action_states_partition',cross.groupby(['cohort','size_group','proxy','proxy_state','activity']).n.sum().eq(cross.groupby(['cohort','size_group','proxy','proxy_state','activity']).N.first()).all())
    weights=load('S7_repeat_initial_weight_records');check('each_initial_study_total_weight_one',np.allclose(weights.groupby(['activity','entry_study_id']).weight.sum(),1))
    check('no_journal_in_main_sources',not any('rank' in v for name in ['Fig3a_entry_uses','Fig3b_repeat12','Fig3c_use_transitions','Fig3d_author_groups','Fig3e_author_use'] for v in load(name).columns))
    for pin in json.loads((OUT/'provenance/input_pins.json').read_text()):check('input_'+str(len(checks)),sha(pin['path'])==pin['sha256'])
    return checks

def technical():
    checks={};fonts=[];metadata=json.loads((OUT/'provenance/figure_metadata.json').read_text());require(len(metadata)==11,'Expected 11 figure groups')
    for row in metadata:
        folder=OUT/'figures'/row['folder'];name=row['figure']
        for ext in ['.pdf','.svg','_600dpi.png','_600dpi.tiff','_preview.png']:require((folder/(name+ext)).is_file(),'Missing figure '+name+ext)
        for ext in ['png','tiff']:
            with Image.open(folder/f'{name}_600dpi.{ext}') as image:
                require(image.mode=='RGB' and bool(image.info.get('icc_profile')) and all(abs(v-600)<.1 for v in image.info.get('dpi',[])),'Raster metadata failure')
                require(abs(image.width/600*25.4-183)<.08,'Native figure width differs')
        require('<text' in (folder/(name+'.svg')).read_text(),'SVG text is not editable')
        result=subprocess.run(['pdffonts',str(folder/(name+'.pdf'))],capture_output=True,text=True,check=True).stdout
        require('TrueType' in result and 'Type 3' not in result,'PDF font embedding failure');fonts.append(dict(figure=name,fonts=result));checks['figure_'+name]=True
    ext=json.loads((OUT/'provenance/text_extents.json').read_text());bad=[v for v in ext if min(v['x0'],v['y0'])<-.002 or max(v['x1'],v['y1'])>1.002]
    dump(OUT/'provenance/clipping_audit.json',dict(text_objects=len(ext),off_canvas=bad));require(not bad,'Text outside figure: '+str(bad[:4]));checks['text_within_canvas']=True
    for letter in 'abcde':require((OUT/'figures/main'/f'Figure3_a_e_panel_{letter}.pdf').is_file(),'Missing separate panel')
    dump(OUT/'provenance/pdf_fonts.json',fonts);checks['five_independent_main_panels']=True
    return checks

if __name__=='__main__':
    check=numeric();check.update(technical());dump(OUT/'provenance/prepublication_audit.json',dict(status='PASS',checks=check,count=len(check)));print('PASS',len(check))
