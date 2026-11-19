"""请求失败与手动恢复不丢失当前图纸、选择和撤销历史。"""
from test_web_connections import connection_scenario


def test_retry_uses_latest_document_and_retains_history_selection_and_draft():
    output = connection_scenario(
        """
      renderSaveState=()=>{};refresh=actualRefresh;
      dirty=true;undo=[{past:true}];redo=[{future:true}];ownedDraft='protected';
      setSelection('node',doc.nodes[0].id);
      api=async()=>{throw Error('服务未连接');};
      results.push(snapshot());await refresh();
      results.push(snapshot(),$('request-banner').hidden);
      doc.nodes[0].x+=7;revision++;const latest=structuredClone(doc);
      const known=new Map(geometries);let received;
      api=async(path,body)=>{received=structuredClone(body.document);
        return {nodes:body.document.nodes.map(n=>({...n,geometry:known.get(n.id)})),
          fontFamily:'serif'};};
      await retryService();
      results.push(snapshot(),{received,latest,hidden:$('request-banner').hidden,
        retryDisabled:$('request-retry').disabled});
    """,
    )
    before, failed, hidden, recovered, detail = output["results"]
    assert not hidden and detail["hidden"] and not detail["retryDisabled"]
    for key in ("doc", "undo", "redo", "selection", "ownedDraft", "dirty"):
        assert before[key] == failed[key]
    for key in ("undo", "redo", "selection", "ownedDraft", "dirty"):
        assert recovered[key] == failed[key]
    assert detail["received"] == detail["latest"] == recovered["doc"]


def test_outdated_failure_does_not_replace_newer_success_with_error_banner():
    output = connection_scenario(
        """
      renderSaveState=()=>{};refresh=actualRefresh;let reject;
      const known=new Map(geometries);let first=true;
      api=async(path,body)=>{if(first){first=false;
        return new Promise((resolve,no)=>{reject=no;});}
        return {nodes:body.document.nodes.map(n=>({...n,geometry:known.get(n.id)})),
          fontFamily:'serif'};};
      const pending=refresh();revision++;doc.title='最新图纸';
      const latest=refresh();reject(Error('旧请求失败'));
      await Promise.all([pending,latest]);
      results.push({hidden:$('request-banner').hidden,title:doc.title});
    """,
    )
    assert output["results"] == [dict(hidden=True, title="最新图纸")]
    assert output["messages"] == []
