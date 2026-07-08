//+------------------------------------------------------------------+
//|                                       EA_TripleEMA_Roll.mq5      |
//|       Trend Following par alignement de 3 EMA + Rolls            |
//+------------------------------------------------------------------+
// Différence vs EA_MoyennesMobiles :
// - EMA (exponentielles, plus réactives) au lieu de SMA
// - 3 niveaux de confirmation au lieu de 2 (alignement complet)
// - Signal : croisement de l'EMA rapide ET alignement total des 3 EMA
//+------------------------------------------------------------------+
#property copyright "Ton Bachelor"
#property version   "1.00"

#include <Trade\Trade.mqh> 
CTrade trade;

// ==========================================
// PARAMÈTRES DE LA STRATÉGIE
// ==========================================
input group "--- Stratégie Triple EMA ---"
input int    InpFastEMA      = 8;       // EMA Rapide
input int    InpMediumEMA    = 21;      // EMA Moyenne
input int    InpSlowEMA      = 55;      // EMA Lente

input group "--- Taille de Position (Money Management) ---"
input double InpRiskPercent  = 2.0;
input bool   InpCompounding  = true;

input group "--- Placement du Risque (Sur le Prix) ---"
input double InpSL_Pct       = 1.0;
input double InpTP_Pct       = 2.0;
input bool   InpUseTrailing  = false;

input group "--- Identification du Robot ---"
input long   InpMagicNumber  = 11002;

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
int emaFastHandle, emaMediumHandle, emaSlowHandle;
double emaFastBuffer[], emaMediumBuffer[], emaSlowBuffer[];
datetime RollDates[];
double SoldeInitial;

double g_equity_curve[];
int    g_equity_count = 0;
double g_initial_equity = 0;

//+------------------------------------------------------------------+
//| INITIALISATION                                                   |
//+------------------------------------------------------------------+
int OnInit()
  {
   Print("🟢 Initialisation EA Triple EMA...");

   SoldeInitial = AccountInfoDouble(ACCOUNT_BALANCE);
   trade.SetExpertMagicNumber(InpMagicNumber);

   g_initial_equity = AccountInfoDouble(ACCOUNT_EQUITY);
   g_equity_count = 0;
   ArrayResize(g_equity_curve, 1);
   g_equity_curve[0] = g_initial_equity;
   g_equity_count = 1;

   ChargerDatesRoll();

   emaFastHandle   = iMA(_Symbol, PERIOD_CURRENT, InpFastEMA,   0, MODE_EMA, PRICE_CLOSE);
   emaMediumHandle = iMA(_Symbol, PERIOD_CURRENT, InpMediumEMA, 0, MODE_EMA, PRICE_CLOSE);
   emaSlowHandle   = iMA(_Symbol, PERIOD_CURRENT, InpSlowEMA,   0, MODE_EMA, PRICE_CLOSE);

   if(emaFastHandle == INVALID_HANDLE || emaMediumHandle == INVALID_HANDLE || emaSlowHandle == INVALID_HANDLE)
     {
      Print("❌ Erreur de création des indicateurs EMA !");
      return(INIT_FAILED);
     }

   ArraySetAsSeries(emaFastBuffer, true);
   ArraySetAsSeries(emaMediumBuffer, true);
   ArraySetAsSeries(emaSlowBuffer, true);

   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   ArrayFree(RollDates);
   ArrayFree(g_equity_curve);
   IndicatorRelease(emaFastHandle);
   IndicatorRelease(emaMediumHandle);
   IndicatorRelease(emaSlowHandle);
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
      // On regarde la bougie 1 (clôturée) et la bougie 2 (avant) pour détecter
      // le passage à un alignement complet (= un vrai changement de régime)
      if(CopyBuffer(emaFastHandle,   0, 0, 3, emaFastBuffer)   <= 0) return;
      if(CopyBuffer(emaMediumHandle, 0, 0, 3, emaMediumBuffer) <= 0) return;
      if(CopyBuffer(emaSlowHandle,   0, 0, 3, emaSlowBuffer)   <= 0) return;

      double fast1   = emaFastBuffer[1];   double fast2   = emaFastBuffer[2];
      double medium1 = emaMediumBuffer[1]; double medium2 = emaMediumBuffer[2];
      double slow1   = emaSlowBuffer[1];   double slow2   = emaSlowBuffer[2];

      // Alignement haussier complet sur bougie 1, pas encore complet sur bougie 2
      bool aligned_up_now    = (fast1 > medium1 && medium1 > slow1);
      bool aligned_up_before = (fast2 > medium2 && medium2 > slow2);

      bool aligned_down_now    = (fast1 < medium1 && medium1 < slow1);
      bool aligned_down_before = (fast2 < medium2 && medium2 < slow2);

      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

      // -- ACHAT : on entre quand l'alignement haussier vient juste d'être formé --
      if(aligned_up_now && !aligned_up_before)
        {
         double sl_price = ask * (1.0 - (InpSL_Pct / 100.0));
         double tp_price = InpUseTrailing ? 0 : ask * (1.0 + (InpTP_Pct / 100.0));
         sl_price = NormalizeDouble(sl_price, _Digits);
         tp_price = NormalizeDouble(tp_price, _Digits);

         double lot_size = CalculerTailleLot(ask, sl_price);
         trade.Buy(lot_size, _Symbol, ask, sl_price, tp_price, "Achat Triple EMA");
        }
      // -- VENTE : alignement baissier qui vient juste de se former --
      else if(aligned_down_now && !aligned_down_before)
        {
         double sl_price = bid * (1.0 + (InpSL_Pct / 100.0));
         double tp_price = InpUseTrailing ? 0 : bid * (1.0 - (InpTP_Pct / 100.0));
         sl_price = NormalizeDouble(sl_price, _Digits);
         tp_price = NormalizeDouble(tp_price, _Digits);

         double lot_size = CalculerTailleLot(bid, sl_price);
         trade.Sell(lot_size, _Symbol, bid, sl_price, tp_price, "Vente Triple EMA");
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
