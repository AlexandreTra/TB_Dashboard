//+------------------------------------------------------------------+
//|                                          EA_ZScore_Roll.mq5      |
//|       Mean Reversion par Z-Score statistique + Rolls             |
//+------------------------------------------------------------------+
// Différence vs EA_MeanReversion (BB+RSI) :
// - Une seule mesure statistique : Z = (close - moyenne) / écart-type
// - Pas de combinaison de 2 indicateurs séparés
// - Le seuil est ajustable et exprime un vrai "nombre d'écarts-types"
// - Approche purement quantitative
//+------------------------------------------------------------------+
#property copyright "Ton Bachelor"
#property version   "1.00"

#include <Trade\Trade.mqh> 
CTrade trade;

// ==========================================
// PARAMÈTRES DE LA STRATÉGIE
// ==========================================
input group "--- Stratégie Z-Score ---"
input int    InpZPeriod      = 20;      // Période pour moyenne + écart-type
input double InpZEntry       = 2.0;     // Seuil d'entrée en nombre d'écarts-types
input double InpZExit        = 0.5;     // Seuil de sortie (sert si trailing OFF)

input group "--- Taille de Position (Money Management) ---"
input double InpRiskPercent  = 2.0;
input bool   InpCompounding  = true;

input group "--- Placement du Risque (Sur le Prix) ---"
input double InpSL_Pct       = 1.0;
input double InpTP_Pct       = 2.0;
input bool   InpUseTrailing  = false;

input group "--- Identification du Robot ---"
input long   InpMagicNumber  = 12002;

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
double closeBuffer[];
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
   Print("🟢 Initialisation EA Z-Score...");

   SoldeInitial = AccountInfoDouble(ACCOUNT_BALANCE);
   trade.SetExpertMagicNumber(InpMagicNumber);

   g_initial_equity = AccountInfoDouble(ACCOUNT_EQUITY);
   g_equity_count = 0;
   ArrayResize(g_equity_curve, 1);
   g_equity_curve[0] = g_initial_equity;
   g_equity_count = 1;

   ChargerDatesRoll();
   ArraySetAsSeries(closeBuffer, true);

   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   ArrayFree(RollDates);
   ArrayFree(g_equity_curve);
  }

//+------------------------------------------------------------------+
//| CALCUL DU Z-SCORE SUR LA BOUGIE 1                                |
//+------------------------------------------------------------------+
double CalculerZScore()
  {
   // On prend les N+1 dernières clôtures pour avoir N points + la bougie 1
   double prices[];
   ArraySetAsSeries(prices, true);
   if(CopyClose(_Symbol, PERIOD_CURRENT, 1, InpZPeriod, prices) <= 0) return 0;

   // Moyenne
   double somme = 0;
   for(int i = 0; i < InpZPeriod; i++) somme += prices[i];
   double moyenne = somme / InpZPeriod;

   // Écart-type
   double somme_carres = 0;
   for(int i = 0; i < InpZPeriod; i++)
      somme_carres += MathPow(prices[i] - moyenne, 2);
   double ecart_type = MathSqrt(somme_carres / InpZPeriod);
   if(ecart_type == 0) return 0;

   // Z-score sur la bougie 1 (la plus récente clôturée)
   return (prices[0] - moyenne) / ecart_type;
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
      double z = CalculerZScore();
      if(z == 0) return;

      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

      // -- ACHAT : prix anormalement bas (Z très négatif) --
      if(z < -InpZEntry)
        {
         double sl_price = ask * (1.0 - (InpSL_Pct / 100.0));
         double tp_price = InpUseTrailing ? 0 : ask * (1.0 + (InpTP_Pct / 100.0));
         sl_price = NormalizeDouble(sl_price, _Digits);
         tp_price = NormalizeDouble(tp_price, _Digits);

         double lot_size = CalculerTailleLot(ask, sl_price);
         trade.Buy(lot_size, _Symbol, ask, sl_price, tp_price, "Achat ZScore");
        }
      // -- VENTE : prix anormalement haut (Z très positif) --
      else if(z > InpZEntry)
        {
         double sl_price = bid * (1.0 + (InpSL_Pct / 100.0));
         double tp_price = InpUseTrailing ? 0 : bid * (1.0 - (InpTP_Pct / 100.0));
         sl_price = NormalizeDouble(sl_price, _Digits);
         tp_price = NormalizeDouble(tp_price, _Digits);

         double lot_size = CalculerTailleLot(bid, sl_price);
         trade.Sell(lot_size, _Symbol, bid, sl_price, tp_price, "Vente ZScore");
        }
     }
   else
     {
      // Sortie sur retour à la moyenne (si trailing pas actif)
      if(!InpUseTrailing)
        {
         double z = CalculerZScore();
         for(int i = PositionsTotal() - 1; i >= 0; i--)
           {
            ulong ticket = PositionGetTicket(i);
            if(PositionGetString(POSITION_SYMBOL) != _Symbol) continue;
            if(PositionGetInteger(POSITION_MAGIC) != InpMagicNumber) continue;

            long type = PositionGetInteger(POSITION_TYPE);
            // Long fermé si Z remonte au-dessus de -InpZExit (proche de zéro)
            if(type == POSITION_TYPE_BUY && z > -InpZExit) trade.PositionClose(ticket);
            // Short fermé si Z redescend en-dessous de +InpZExit
            else if(type == POSITION_TYPE_SELL && z < InpZExit) trade.PositionClose(ticket);
           }
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
