"""Frozen v1 percentile algorithm reused exactly; no acquisition code."""
from common import *
def reference_percentiles(x,count_col,mature_col,min_n=100):
 good=x[count_col].notna()&x[mature_col].fillna(False)&x.subfield.notna()
 groups={key:g for key,g in x.groupby(['subfield','year','month','work_type'],dropna=False)}
 parent_groups={key:g for key,g in x.groupby(['parent_field','year','month','work_type'],dropna=False)}
 out=pd.Series(np.nan,index=x.index);audit=[]
 # Each target's reference pool includes every label/group, never just AF.
 for key,g in groups.items():
  sf,y,m,typ=key;ref=None;mode=None;radius=None
  if pd.isna(sf):continue
  if not good.reindex(g.index).any():continue
  for r in [0,1,2]:
   parts=[groups[k] for k in [(sf,y,mm,typ) for mm in range(max(1,int(m)-r),min(12,int(m)+r)+1)] if k in groups]
   z=pd.concat(parts);v=z.loc[good.reindex(z.index),count_col].to_numpy()
   if len(v)>=min_n:ref=z;mode='subfield';radius=r;break
  if ref is None:
   parent=g.parent_field.iloc[0]
   if pd.notna(parent):
    for r in [0,1,2,12]:
     parts=[parent_groups[k] for k in [(parent,y,mm,typ) for mm in range(max(1,int(m)-r),min(12,int(m)+r)+1)] if k in parent_groups]
     if not parts:continue
     z=pd.concat(parts)
     v=z.loc[good.reindex(z.index),count_col].to_numpy()
     if len(v)>=min_n:ref=z;mode='parent_field';radius=r;break
  valid=g[good.reindex(g.index)]
  if ref is not None:
   vals=np.sort(ref.loc[good.reindex(ref.index),count_col].to_numpy());target=valid[count_col].to_numpy()
   percentile=(np.searchsorted(vals,target,'left')+np.searchsorted(vals,target,'right'))/(2*len(vals))*100
   out.loc[valid.index]=percentile
   refpct=(np.searchsorted(vals,vals,'left')+np.searchsorted(vals,vals,'right'))/(2*len(vals))*100
   audit.append(dict(window=count_col,subfield=sf,year=y,month=m,work_type=typ,mode=mode,radius=radius,reference_n=len(vals),reference_total=len(ref),known_fraction=len(vals)/len(ref),qualifying90=float(np.mean(refpct>=90)),qualifying95=float(np.mean(refpct>=95))))
  else:audit.append(dict(window=count_col,subfield=sf,year=y,month=m,work_type=typ,mode='insufficient',radius=None,reference_n=len(v) if 'v' in locals() else 0,reference_total=len(g),known_fraction=None,qualifying90=None,qualifying95=None))
 return out,pd.DataFrame(audit)
