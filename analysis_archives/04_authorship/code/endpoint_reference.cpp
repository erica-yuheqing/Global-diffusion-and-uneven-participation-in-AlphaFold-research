// Actual within-study ordered distinct-author simulations. No synthetic empirical input.
#include <cstdint>
#include <random>
#include <vector>
#include <cstdio>
extern "C" int endpoints(
 int64_t B,uint64_t seed,int64_t N,const int64_t* pool_ptr,const int64_t* pool_authors,
 const double* group_weights,const int64_t* country_ptr,const int32_t* country_idx,const double* country_weight,
 const int64_t* inst_ptr,const int32_t* inst_entity,int64_t nEntity,const int32_t* entity_view,const int8_t* entity_role_valid,int64_t nView,
 const int8_t* inst_eligible,const int8_t* corpus,const double* weights,
 double* group_out,int32_t* zero_out,int32_t* entity_zero){
 std::mt19937_64 rng(seed);std::vector<int32_t> seenF(nEntity,-1),seenL(nEntity,-1);
 for(int64_t b=0;b<B;++b){
  for(int64_t s=0;s<N;++s){
   const int64_t n=pool_ptr[s+1]-pool_ptr[s];
   if(n<2 || (weights[s*2]==0 && weights[s*2+1]==0 && !inst_eligible[s]))continue;
   std::uniform_int_distribution<int64_t> first(0,n-1),last(0,n-2);
   int64_t i=first(rng),j=last(rng);if(j>=i)++j;
   const int64_t a=pool_authors[pool_ptr[s]+i],d=pool_authors[pool_ptr[s]+j];
   if(a==d)return 11;
   if(weights[s*2]>0 || weights[s*2+1]>0){
    double same=0;int64_t x=country_ptr[a],y=country_ptr[d];
    while(x<country_ptr[a+1] && y<country_ptr[d+1]){
     if(country_idx[x]==country_idx[y]){same+=country_weight[x]*country_weight[y];++x;++y;}
     else if(country_idx[x]<country_idx[y])++x;else ++y;
    }
    for(int setting=0;setting<2;++setting){
     const double w=weights[s*2+setting];if(w==0)continue;
     double* out=group_out+(((b*2+corpus[s])*2+setting)*18);
     for(int g=0;g<4;++g)if(group_weights[a*4+g]>0)
      for(int h=0;h<4;++h)if(group_weights[d*4+h]>0)out[g*4+h]+=w*group_weights[a*4+g]*group_weights[d*4+h];
     out[16]+=w*same;out[17]+=w;
    }
   }
   if(inst_eligible[s]){
    for(int64_t x=inst_ptr[a];x<inst_ptr[a+1];++x)seenF[inst_entity[x]]=int32_t(b);
    for(int64_t x=inst_ptr[d];x<inst_ptr[d+1];++x)seenL[inst_entity[x]]=int32_t(b);
   }
  }
  for(int64_t e=0;e<nEntity;++e){
   if(seenF[e]!=b){if(entity_role_valid[e*2])++zero_out[(b*nView+entity_view[e])*2];++entity_zero[e*2];}
   if(seenL[e]!=b){if(entity_role_valid[e*2+1])++zero_out[(b*nView+entity_view[e])*2+1];++entity_zero[e*2+1];}
  }
  if((b+1)%100==0){std::printf("Conditional distinct-author reference %lld/%lld\n",(long long)b+1,(long long)B);std::fflush(stdout);}
 }
 return 0;
}
