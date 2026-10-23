import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {runExitStudy} from './exit_study.mjs';
const base=path.dirname(fileURLToPath(import.meta.url));
const result=await runExitStudy({
 root:path.join(base,'data'),out:path.join(base,'results'),
 schedulePath:path.join(base,'dividends_verified.json')
});
console.log(JSON.stringify({main:result.summaries.length,sensitivity:result.sensitivity.length,verification:result.testNames},null,2));

