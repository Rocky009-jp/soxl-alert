import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {runComparison} from './compare_initial_trend.mjs';
const base=path.dirname(fileURLToPath(import.meta.url));
const result=await runComparison({
 root:path.join(base,'data'),out:path.join(base,'results'),
 schedulePath:path.join(base,'dividends_verified.json'),
 previousSummaryPath:path.join(base,'previous_dividend_summary.csv')
});
console.log(JSON.stringify({main_cases:result.summaries.length,sensitivity_cases:result.sensitivity.length,
 rankings:result.ranking,verification:result.passed},null,2));

