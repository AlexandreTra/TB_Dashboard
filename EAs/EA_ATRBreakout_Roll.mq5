//+------------------------------------------------------------------+
//|                                     EA_ATRBreakout_Roll.mq5      |
//|       Breakout adaptatif à la volatilité (ATR) + Rolls           |
//+------------------------------------------------------------------+
// Différence vs EA_Breakout (Donchian) :
// - Niveaux de cassure dynamiques basés sur l'ATR (et non plus les
//   plus hauts/bas absolus sur N bougies).
// - Niveau haut  = SMA + k * ATR
// - Niveau bas   = SMA - k * ATR
// - Plus serré en marché calme, plus large en marché volatil.
// - Confirme que le mouvement est statistiquement significatif vs
//   la volatilité du moment.
//+------------------------------------------------------------------+
#property copyright "Ton Bachelor"
#property version   "1.00"

#include <Trade\Trade.mqh> 
CTrade trade;

// ==========================================
// PARAMÈTRES DE LA STRATÉGIE
// ==========================================
input group "--- Stratégie ATR Breakout ---"
input int    InpAtrPeriod    = 14;      // Période de l'ATR
input int    InpSmaPeriod    = 20;      // Période de la moyenne centrale
input double InpAtrMultiplier= 2.0;     // Multiplicateur ATR (k)

input group "--- Taille de Position (Money Management) ---"
input double InpRiskPercent  = 2.0;
input bool   InpCompounding  = true;

input group "--- Placement du Risque (Sur le Prix) ---"
input double InpSL_Pct       = 1.0;
input double InpTP_Pct       = 2.0;
input bool   InpUseTrailing  = false;

input group "--- Identification du Robot ---"
input long   InpMagicNumber  = 13002;

input group "--- Gestion des Rollovers ---"
input string InpFileName     = "dates_rolls.csv";
input int    InpJoursAvant   = 4;
input int    InpJoursApres   = 2;

input group "--- Optimizer Score ---"
input double Score_MinProfitFactor = 1.2;
input double Score_MaxDrawdownPct  = 20.0;
input int    Score_MinTrades       = 30;
input double Score_R2Weight        = 0.7;
input double Score_SlopeWeight     = 0.3;

// ==========================================
// VARIABLES GLOBALES
// ==========================================
int atrHandle, smaHandle;
double atrBuffer[], smaBuffer[], closeBuffer[];
datetime RollDates[];
double SoldeInitial;

double g_equity_curve[];
int    g_equity_count = 0;
double g_initial_equity = 0;

//+------------------------------------------------------------------+
//| INIT                                                             |
//+------------------------------------------------------------------+
int OnInit()
  {
   Print("🟢 Initialisation EA ATR Breakout...");

   SoldeInitial = AccountInfoDouble(ACCOUNT_BALANCE);
   trade.SetExpertMagicNumber(InpMagicNumber);

   g_initial_equity = AccountInfoDouble(ACCOUNT_EQUITY);
   g_equity_count = 0;
   ArrayResize(g_equity_curve, 1);
   g_equity_curve[0] = g_initial_equity;
   g_equity_count = 1;

   ChargerDatesRoll();

   atrHandle = iATR(_Symbol, PERIOD_CURRENT, InpAtrPeriod);
   smaHandle = iMA(_Symbol, PERIOD_CURRENT, InpSmaPeriod, 0, MODE_SMA, PRICE_CLOSE);

   if(atrHandle == INVALID_HANDLE || smaHandle == INVALID_HANDLE)
     {
      Print("❌ Erreur de création des indicateurs ATR/SMA !");
      return(INIT_FAILED);
     }

   ArraySetAsSeries(atrBuffer, true);
   ArraySetAsSeries(smaBuffer, true);
   ArraySetAsSeries(closeBuffer, true);

   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   ArrayFree(RollDates);
   ArrayFree(g_equity_curve);
   IndicatorRelease(atrHandle);
   IndicatorRelease(smaHandle);
  }

//+------------------------------------------------------------------+
//| ONTICK                                                           |
//+------------------------------------------------------------------+
void OnTick()
  {
   if(EstEnZoneRoll())
     {
      if(PositionsTotal() > 0)
        {
         Print("⚠️ ZONE DE ROLLOVER : Fermeture d'urgence !");
         FermerToutesLesPositions();
        }
      return;
     }

   if(InpUseTrailing && PositionsTotal() > 0)
      GererStopSuiveur();

   if(PositionsTotal() == 0)
     {
      // On lit l'ATR, la SMA et la clôture de la bougie 1 (clôturée)
      if(CopyBuffer(atrHandle, 0, 1, 1, atrBuffer) <= 0) return;
      if(CopyBuffer(smaHandle, 0, 1, 1, smaBuffer) <= 0) return;
      if(CopyClose(_Symbol, PERIOD_CURRENT, 1, 1, closeBuffer) <= 0) return;

      double atr   = atrBuffer[0];
      double sma   = smaBuffer[0];
      double close1 = closeBuffer[0];

      double upper_band = sma + (InpAtrMultiplier * atr);
      double lower_band = sma - (InpAtrMultiplier * atr);

      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

      // -- CASSURE HAUSSIÈRE adaptative --
      if(close1 > upper_band)
        {
         double sl_price = ask * (1.0 - (InpSL_Pct / 100.0));
         double tp_price = InpUseTrailing ? 0 : ask * (1.0 + (InpTP_Pct / 100.0));
         sl_price = NormalizeDouble(sl_price, _Digits);
         tp_price = NormalizeDouble(tp_price, _Digits);

         double lot_size = CalculerTailleLot(ask, sl_price);
         trade.Buy(lot_size, _Symbol, ask, sl_price, tp_price, "Achat ATR Breakout");
        }
      // -- CASSURE BAISSIÈRE adaptative --
      else if(close1 < lower_band)
        {
         double sl_price = bid * (1.0 + (InpSL_Pct / 100.0));
         double tp_price = InpUseTrailing ? 0 : bid * (1.0 - (InpTP_Pct / 100.0));
         sl_price = NormalizeDouble(sl_price, _Digits);
         tp_price = NormalizeDouble(tp_price, _Digits);

         double lot_size = CalculerTailleLot(bid, sl_price);
         trade.Sell(lot_size, _Symbol, bid, sl_price, tp_price, "Vente ATR Breakout");
        }
     }
  }

//+------------------------------------------------------------------+
//| HELPERS                                                          |
//+------------------------------------------------------------------+
double CalculerTailleLot(double prix_entree, double prix_stoploss)
  {
   double capital_reference = InpCompounding ? AccountInfoDouble(ACCOUNT_BALANCE) : SoldeInitial;
   double risque_argent = capital_reference * (InpRiskPercent / 100.0);
   double distance_sl_prix = MathAbs(prix_entree - prix_stoploss);

   double tick_size = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tick_value = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   if(tick_size == 0 || tick_value == 0) return SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);

   double perte_pour_1_lot = (distance_sl_prix / tick_size) * tick_value;
   if(perte_pour_1_lot == 0) return SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);

   double lot_calcule = risque_argent / perte_pour_1_lot;
   double lot_step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double lot_min  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double lot_max  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);

   lot_calcule = MathFloor(lot_calcule / lot_step) * lot_step;
   if(lot_calcule < lot_min) lot_calcule = lot_min;
   if(lot_calcule > lot_max) lot_calcule = lot_max;
   return lot_calcule;
  }

void FermerToutesLesPositions()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
         trade.PositionClose(ticket);
     }
  }

void GererStopSuiveur()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
        {
         double current_sl = PositionGetDouble(POSITION_SL);
         double current_price = PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
         double distance = current_price * (InpSL_Pct / 100.0);

         if(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY)
           {
            double new_sl = NormalizeDouble(current_price - distance, _Digits);
            if((new_sl > current_sl && current_sl != 0) || current_sl == 0)
               trade.PositionModify(ticket, new_sl, 0);
           }
         else
           {
            double new_sl = NormalizeDouble(current_price + distance, _Digits);
            if((new_sl < current_sl && current_sl != 0) || current_sl == 0)
               trade.PositionModify(ticket, new_sl, 0);
           }
        }
     }
  }

void ChargerDatesRoll()
  {
   int handle = FileOpen(InpFileName, FILE_READ|FILE_CSV|FILE_ANSI, ',');
   if(handle == INVALID_HANDLE) return;
   string my_symbol = _Symbol;
   StringToUpper(my_symbol);

   while(!FileIsEnding(handle))
     {
      string sym = FileReadString(handle);
      string dte = FileReadString(handle);
      if(sym == "") continue;
      StringToUpper(sym);

      if(sym == my_symbol || StringFind(my_symbol, sym) >= 0)
        {
         int taille = ArraySize(RollDates);
         ArrayResize(RollDates, taille + 1);
         RollDates[taille] = StringToTime(dte);
        }
     }
   FileClose(handle);
  }

bool EstEnZoneRoll()
  {
   datetime maintenant = TimeCurrent();
   for(int i = 0; i < ArraySize(RollDates); i++)
     {
      datetime debut_zone = RollDates[i] - (InpJoursAvant * 86400);
      datetime fin_zone   = RollDates[i] + (InpJoursApres * 86400);
      if(maintenant >= debut_zone && maintenant <= fin_zone) return true;
     }
   return false;
  }

void PushEquitySnapshot()
  {
   ArrayResize(g_equity_curve, g_equity_count + 1);
   g_equity_curve[g_equity_count++] = AccountInfoDouble(ACCOUNT_EQUITY);
  }

void OnTradeTransaction(const MqlTradeTransaction& trans,
                        const MqlTradeRequest&     request,
                        const MqlTradeResult&      result)
  {
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD) return;
   ulong deal_ticket = trans.deal;
   if(!HistoryDealSelect(deal_ticket)) return;

   long magic = HistoryDealGetInteger(deal_ticket, DEAL_MAGIC);
   long entry = HistoryDealGetInteger(deal_ticket, DEAL_ENTRY);
   string sym = HistoryDealGetString(deal_ticket, DEAL_SYMBOL);

   if(magic == InpMagicNumber && sym == _Symbol && entry == DEAL_ENTRY_OUT)
      PushEquitySnapshot();
  }

double OnTester()
  {
   int total_trades = (int)TesterStatistics(STAT_TRADES);

   if(TesterStatistics(STAT_PROFIT) <= 0) return 0;
   if(TesterStatistics(STAT_PROFIT_FACTOR) < Score_MinProfitFactor) return 0;
   if(TesterStatistics(STAT_EQUITY_DDREL_PERCENT) > Score_MaxDrawdownPct) return 0;
   if(total_trades < Score_MinTrades) return 0;
   if(g_equity_count < 5) return 0;

   double n = (double)g_equity_count;
   double sum_x=0, sum_y=0, sum_xx=0, sum_xy=0;
   for(int i = 0; i < g_equity_count; i++)
     {
      sum_x  += i;
      sum_y  += g_equity_curve[i];
      sum_xx += (double)i * i;
      sum_xy += (double)i * g_equity_curve[i];
     }

   double denom = n * sum_xx - sum_x * sum_x;
   if(denom == 0) return 0;

   double slope = (n * sum_xy - sum_x * sum_y) / denom;
   double intercept = (sum_y - slope * sum_x) / n;
   if(slope <= 0) return 0;

   double ss_res=0, ss_tot=0, mean_y = sum_y / n;
   for(int i = 0; i < g_equity_count; i++)
     {
      double predicted = slope * i + intercept;
      ss_res += MathPow(g_equity_curve[i] - predicted, 2);
      ss_tot += MathPow(g_equity_curve[i] - mean_y, 2);
     }
   if(ss_tot == 0) return 0;

   double r2 = 1.0 - (ss_res / ss_tot);
   if(r2 <= 0) return 0;

   double slope_normalized = (slope / g_initial_equity) * 100.0;
   return (Score_R2Weight * r2) + (Score_SlopeWeight * slope_normalized);
  }
