import {build} from './build_audit.mjs';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
const base=path.dirname(fileURLToPath(import.meta.url));
const result=await build(path.join(base,'data'),path.join(base,'results'),path.join(base,'dividends_verified.json'));
console.log(JSON.stringify({tests:result.tests.passed,legacy_reconciliation:result.rec,intraday_dates:result.dates},null,2));

