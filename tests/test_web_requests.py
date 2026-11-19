"""直接导入前端模块：合并解析请求且不让失败阻塞后续更新。"""

import base64
import json
import shutil
import subprocess
from pathlib import Path

import pytest


def run_module(name, script):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node not installed")
    path = Path(__file__).resolve().parents[1] / "web" / name
    url = "data:text/javascript;base64," + base64.b64encode(path.read_bytes()).decode()
    result = subprocess.run(
        [
            node,
            "--input-type=module",
            "-e",
            f"const module = await import({json.dumps(url)});" + script,
        ],
        capture_output=True,
        encoding="utf-8",
        check=True,
        timeout=10,
    )
    return json.loads(result.stdout)


def test_queue_keeps_only_latest_pending_request():
    result = run_module(
        "requests.js",
        """
      const sent=[], release=[]; let active=0,max=0;
      const queue=module.createLatestQueue(value=>new Promise(resolve=>{
        sent.push(value);max=Math.max(max,++active);
        release.push(()=>{active--;resolve(value*10);});}));
      const first=queue(1);await Promise.resolve();
      const second=queue(2),third=queue(3);
      release.shift()();const a=await first;await Promise.resolve();
      release.shift()();const values=await Promise.all([second,third]);
      console.log(JSON.stringify({sent,max,values:[a,...values]}));
    """,
    )
    assert result == dict(sent=[1, 3], max=1, values=[10, None, 30])


def test_synchronous_updates_keep_first_and_latest_snapshot():
    assert run_module(
        "requests.js",
        """
      const sent=[];const queue=module.createLatestQueue(async x=>{
        sent.push(x);return x;});
      const result=await Promise.all([queue(1),queue(2),queue(3)]);
      console.log(JSON.stringify({sent,result}));
    """,
    ) == dict(sent=[1, 3], result=[1, None, 3])


def test_failed_request_does_not_block_following_snapshot():
    result = run_module(
        "requests.js",
        """
      let fail;const queue=module.createLatestQueue(x=>x===1
        ? new Promise((resolve,reject)=>{fail=reject;}) : Promise.resolve(x));
      const first=queue(1).catch(e=>e.message);await Promise.resolve();
      const last=queue(2);fail(Error('failed'));
      console.log(JSON.stringify(await Promise.all([first,last])));
    """,
    )
    assert result == ["failed", 2]


def test_service_status_distinguishes_offline_legacy_and_changed_code():
    values = run_module(
        "service.js",
        """
      console.log(JSON.stringify([null,{ok:true,version:'1.0'},
        {ok:true,version:'1.3',app:'rrplot',instanceId:'a',codeChanged:false},
        {ok:true,version:'1.3',app:'rrplot',instanceId:'a',codeChanged:true}]
        .map(module.serviceStatus)));
    """,
    )
    assert [item["warning"] for item in values] == [True, True, False, True]
    assert "旧版" in values[1]["text"]
    assert "需要重启" in values[3]["text"]
    assert "restart-web.cmd" in values[3]["detail"]
