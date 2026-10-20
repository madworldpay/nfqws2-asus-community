import assert from 'node:assert/strict';
import { test } from 'node:test';
import { emptyProfile, newUpstream, editProfile, acceptPreview, remainingSeconds, withDomain } from '../webui/web/src/api/smartDnsProfile.ts';
test('a new profile does not silently pick a household DNS',()=>{assert.deepEqual(emptyProfile().upstreams,[]);assert.equal(newUpstream('a').address,'');});
test('editing invalidates the viewed preview and a late response cannot restore it',()=>{
 const state={profile:emptyProfile(),revision:2,preview:{id:'old'}};const edited=editProfile(state,{...emptyProfile(),upstreams:[newUpstream('a')]});
 assert.equal(edited.preview,null);assert.equal(edited.revision,3);assert.equal(acceptPreview(edited,2,{id:'late'}),edited);assert.equal(acceptPreview(edited,3,{id:'current'}).preview.id,'current');
});
test('domain scope survives editing and distinguishes exact from suffix',()=>{
 const p={...emptyProfile(),upstreams:[newUpstream('a')]};const exact=withDomain(p,0,{name:'image.tmdb.org',include_subdomains:false});
 const suffix=withDomain(exact,0,{name:'example.org',include_subdomains:true});assert.equal(suffix.upstreams[0].domains[0].include_subdomains,false);assert.equal(suffix.upstreams[0].domains[1].include_subdomains,true);assert.equal(p.upstreams[0].domains.length,0);
});
test('confirmation countdown uses server duration and monotonic elapsed time',()=>{assert.equal(remainingSeconds(120,1000,31000),90);assert.equal(remainingSeconds(10,1000,99000),0);assert.equal(remainingSeconds(null,0,0),null);});
