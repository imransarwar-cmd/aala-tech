// Actual helpers/patch/component methods with test doubles; not a live Owl mount.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const source = (name) => fs.readFileSync(path.join(root, 'static/src', name), 'utf8');
const importCode = (code) => import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));
const helpers = await importCode(source('preview_helpers.js'));
const att = { id: 1, name: 'Book.xlsx', type: 'binary', uploading: false };

test('recognizes supported names case-insensitively', () => {
    for (const name of ['BOQ.XLSX', 'BOQ.xlsm', 'mapping.csv']) assert.equal(helpers.canPreviewSpreadsheet({...att, name}), true);
});
test('does not intercept unsupported native files', () => {
    for (const name of ['photo.jpg', 'drawing.pdf', 'old.xls', 'file.xlsx.exe']) assert.equal(helpers.canPreviewSpreadsheet({...att, name}), false);
});
test('does not intercept links and unfinished uploads', () => {
    assert.equal(helpers.canPreviewSpreadsheet({...att, type:'url'}), false);
    assert.equal(helpers.canPreviewSpreadsheet({...att, uploading:true}), false);
    assert.equal(helpers.canPreviewSpreadsheet({...att, id:-1}), false);
    assert.equal(helpers.canPreviewSpreadsheet({...att, id:'1'}), false);
});
test('allows only safe style values', () => {
    const value = helpers.cellStyle({color:'red; background:url(https://bad)', background:'#ABCDEF', align:'left;display:none', bold:true});
    assert.equal(value, 'font-weight:700;background-color:#ABCDEF');
});
test('search is case-insensitive plain text, not regex or markup', () => {
    assert.equal(helpers.matchesText('SO223', 'so22'), true);
    assert.equal(helpers.matchesText('SO223', '.*'), false);
    assert.equal(helpers.matchesText('SO223', ''), false);
});

let extension;
class AttachmentList {
    onClickAttachment(a) { this.nativeCalls = (this.nativeCalls || 0) + 1; return 'native'; }
    getActions() { return [{label:'Download'}]; }
}
globalThis.__dvzPatchTest = {
    AttachmentList,
    _t:s=>s,
    ExcelPreviewDialog: class {},
    canPreviewSpreadsheet:helpers.canPreviewSpreadsheet,
    patch(proto, ext) {
        Object.setPrototypeOf(ext, Object.create(null, Object.getOwnPropertyDescriptors(proto)));
        Object.defineProperties(proto, Object.getOwnPropertyDescriptors(ext));
        extension=ext;
    },
};
await importCode('const { AttachmentList, _t, ExcelPreviewDialog, canPreviewSpreadsheet, patch } = globalThis.__dvzPatchTest;\n' + source('attachment_list_patch.js').replace(/^import .*;\n/gm,''));
function list() {
    const l = new AttachmentList(); l.calls=[];
    l.dialog={add(...args){l.calls.push(args);return ()=>{};}};
    return l;
}
test('native attachment click opens one Excel dialog', () => {
    const l=list(); l.onClickAttachment(att); l.onClickAttachment(att);
    assert.equal(l.calls.length,1); assert.equal(l.calls[0][1].attachmentId,1);
});
test('closing permits reopening', () => {
    const l=list(); l.onClickAttachment(att); l.calls[0][2].onClose(); l.onClickAttachment(att);
    assert.equal(l.calls.length,2);
});
test('PDF uses original method', () => {
    const l=list(); assert.equal(l.onClickAttachment({...att,name:'doc.pdf'}),'native');
    assert.equal(l.nativeCalls,1); assert.equal(l.calls.length,0);
});
test('download action retained with preview action', () => {
    const l=list(); const actions=l.getActions(att);
    assert.equal(actions[0].label,'Preview spreadsheet'); assert.equal(actions[1].label,'Download');
});
test('dialog setup failure releases click guard', () => {
    const l=list(); l.dialog.add=()=>{throw Error('test');};
    assert.throws(()=>l.onClickAttachment(att)); assert.equal(l._dvzExcelPreviewOpen,false);
});

const callbacks=[];
const fakeORM={call:async()=>({rows:[],sheets:[],preview_rows:0})};
globalThis.__dvzDialogTest = {
    Component:class {}, Dialog:class {},
    onMounted:()=>{}, onWillDestroy:fn=>callbacks.push(fn), useState:x=>x,
    useRef:()=>({el:null}), useService:()=>fakeORM,
    _t:(s,...args)=>args.reduce((text,value)=>text.replace('%s',value),s),
    downloadFile:()=>{}, ...helpers,
};
const dialog = await importCode('const { Component, Dialog, onMounted, onWillDestroy, useRef, useState, useService, _t, downloadFile, cellStyle, matchesText } = globalThis.__dvzDialogTest;\n' + source('excel_preview_dialog.js').replace(/^import .*;\n/gm,''));
function component() {
    const c=new dialog.ExcelPreviewDialog(); c.props={attachmentId:7,filename:'BOQ.xlsx',close:()=>{}}; c.setup(); return c;
}
test('RPC sends only attachment id and page selector', async () => {
    let args; fakeORM.call=async(...a)=>{args=a;return {rows:[],sheets:[],preview_rows:0};};
    const c=component(); await c.load(2,100);
    assert.deepEqual(args,['ir.attachment','dvz_excel_preview',[[7]],{sheet_index:2,offset:100}]);
    assert.equal(c.state.loading,false);
});
test('failed permission check clears stale cells', async () => {
    fakeORM.call=async()=>{throw {data:{message:'Access denied'}};};
    const c=component(); c.state.data={rows:[{text:'old'}]}; await c.load(0,0);
    assert.equal(c.state.data,null); assert.equal(c.state.error,'Access denied');
});
test('stale RPC responses do not overwrite newer sheet', async () => {
    const resolvers=[]; fakeORM.call=()=>new Promise(resolve=>resolvers.push(resolve));
    const c=component(); const first=c.load(0,0); const second=c.load(1,0);
    resolvers[1]({sheet_name:'Second',rows:[]}); await second;
    resolvers[0]({sheet_name:'First',rows:[]}); await first;
    assert.equal(c.state.data.sheet_name,'Second');
});
test('destroyed component ignores response', async () => {
    let resolve; fakeORM.call=()=>new Promise(r=>{resolve=r;});
    const c=component(); const loading=c.load(0,0); callbacks.at(-1)(); resolve({sheet_name:'Ignored'}); await loading;
    assert.equal(c.state.data,null);
});
