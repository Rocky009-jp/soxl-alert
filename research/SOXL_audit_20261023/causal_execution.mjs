import {saleFloor,sellCosts,TAX,commission,quantity,invariant} from './audit.mjs';
import assert from 'node:assert/strict';
// Pure research module. No broker adapter, credentials, HTTP calls or live orders.
export function compileSell(account,decision,{date,submitted_ms,kind='MARKET',strictNoLoss=true}) {
  assert(decision.available_ms<=submitted_ms,'Future decision data');
  if(!account.shares)return {status:'NO_POSITION'};
  if(strictNoLoss&&kind==='MARKET')return {status:'INCOMPATIBLE',reason:'Unbounded market execution cannot guarantee no-loss sale'};
  return {status:'DRAFT',side:'SELL',kind,submitted_ms,quantity:account.shares,basis:account.basis,
    date,limit:kind==='LIMIT'?saleFloor(account.shares,account.basis,date):null};
}
export function compileBuy(account,decision,quote,{submitted_ms,fraction=1,buffer=.01}) {
  assert(decision.available_ms<=submitted_ms,'Future decision');
  assert(quote.observed_ms<=submitted_ms,'Future sizing quote');
  assert(submitted_ms-quote.observed_ms<=1000,'Stale sizing quote');
  assert(quote.ask>0&&quote.ask>=quote.bid,'Invalid sizing quote');
  return {status:'DRAFT',side:'BUY',kind:'MARKET',submitted_ms,
    quantity:quantity(account.cash*fraction,quote.ask*(1+buffer)),date:decision.execution_date};
}
export function quoteModel(account,order,quote,{arrival_ms,maxAge_ms=1000}={}) {
  // NBBO-only counterfactual, not a reconstructed actual fill. No queue or hidden liquidity assumed.
  if(order.status!=='DRAFT')return {status:'NO_ORDER'};
  assert(arrival_ms>=order.submitted_ms,'Execution precedes submission');
  assert(quote.observed_ms<=arrival_ms,'Quote after arrival');
  if(arrival_ms-quote.observed_ms>maxAge_ms)return {status:'STALE'};
  if(!(quote.ask>=quote.bid&&quote.bid>0))return {status:'INVALID_QUOTE'};
  const n=order.quantity;
  if(n===0)return {status:'ZERO_QUANTITY'};
  const px=order.side==='SELL'?quote.bid:quote.ask;
  const size=order.side==='SELL'?quote.bid_size_shares:quote.ask_size_shares;
  if(size<n)return {status:'DEPTH_INSUFFICIENT_UNCONFIRMED'};
  if(order.kind==='LIMIT'&&order.side==='SELL'&&px<order.limit)return {status:'NOT_MARKETABLE_RETAIN_POSITION'};
  const fee=order.side==='SELL'?sellCosts(n,px,order.date):commission(n*px);
  if(order.side==='BUY'&&n*px+fee>account.cash)return {status:'FUNDING_EXCEEDED_UNCONFIRMED'};
  const gain=order.side==='SELL'?n*px-fee-order.basis:0;
  if(order.side==='SELL'&&order.kind==='LIMIT')assert(gain+1e-8>=order.basis*.02);
  return {status:'QUOTE_MODEL_ONLY',quantity:n,price:px,fee,tax:Math.max(0,gain)*TAX,arrival_ms};
}

