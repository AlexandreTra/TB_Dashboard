//+------------------------------------------------------------------+
//|                                    EA_MoyennesMobiles_Roll.mq5   |
//|               Croisement MA + Money Management % + Rolls         |
//+------------------------------------------------------------------+
#property copyright "Ton Bachelor"
#property version   "1.20"

#include <Trade\Trade.mqh> 
CTrade trade;

// ==========================================
// PARAMÈTRES DE LA STRATÉGIE
// ==========================================
input group "--- Stratégie Moyennes Mobiles ---"
input int    InpFastMA       = 10;      // Période Moyenne Rapide
input int    InpSlowMA       = 50;      // Période Moyenne Lente

input group "--- Taille de Position (Money Management) ---"
input double InpRiskPercent  = 2.0;     // Risque par trade (en % du capital)
input bool   InpCompounding  = true;    // True = Intérêts Composés (Solde Actuel) | False = Solde de Départ

input group "--- Placement du Risque (Sur le Prix) ---"
input double InpSL_Pct       = 1.0;     // Stop Loss en % du Prix
input double InpTP_Pct       = 2.0;     // Take Profit en % du Prix
input bool   InpUseTrailing  = false;   // True = Stop Suiveur | False = TP Fixe

input group "--- Identification du Robot ---"
input long   InpMagicNumber  = 11001;   // Magic Number (unique par EA)

input group "--- Gestion des Rollovers ---"
input string InpFileName     = "dates_rolls.csv"; // Fichier des dates
input int    InpJoursAvant   = 4;       // Bloquer X jours AVANT
input int    InpJoursApres   = 2;       // Bloquer X jours APRÈS

input group "--- Optimizer Score ---"
input double Score_MinProfitFactor = 1.2;
input double Score_MaxDrawdownPct  = 20.0;
input int    Score_MinTrades       = 30;
input double Score_R2Weight        = 0.7;
input double Score_SlopeWeight     = 0.3;

// ==========================================
// VARIABLES GLOBALES
// ==========================================
int maFastHandle, maSlowHandle;
double maFastBuffer[], maSlowBuffer[];
datetime RollDates[];
double SoldeInitial;

// Pour le score
double g_equity_curve[];
int    g_equity_count = 0;
double g_initial_equity = 0;

//+------------------------------------------------------------------+
//| 1. INITIALISATION DU ROBOT                                       |
//+------------------------------------------------------------------+
int OnInit()
  {
   Print("🟢 Initialisation EA Moyennes Mobiles...");

   SoldeInitial = AccountInfoDouble(ACCOUNT_BALANCE);

   // Magic number pour identifier les trades de cet EA
   trade.SetExpertMagicNumber(InpMagicNumber);

   // Initialisation de la courbe d'équité pour le scoring
   g_initial_equity = AccountInfoDouble(ACCOUNT_EQUITY);
   g_equity_count = 0;
   ArrayResize(g_equity_curve, 1);
   g_equity_curve[0] = g_initial_equity;
   g_equity_count = 1;

   ChargerDatesRoll();

   maFastHandle = iMA(_Symbol, PERIOD_CURRENT, InpFastMA, 0, MODE_SMA, PRICE_CLOSE);
   maSlowHandle = iMA(_Symbol, PERIOD_CURRENT, InpSlowMA, 0, MODE_SMA, PRICE_CLOSE);

   if(maFastHandle == INVALID_HANDLE || maSlowHandle == INVALID_HANDLE)
     {
      Print("❌ Erreur de création des indicateurs MA !");
      return(INIT_FAILED);
     }

   ArraySetAsSeries(maFastBuffer, true);
   ArraySetAsSeries(maSlowBuffer, true);

   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   ArrayFree(RollDates);
   ArrayFree(g_equity_curve);
   IndicatorRelease(maFastHandle);
   IndicatorRelease(maSlowHandle);
  }

//+------------------------------------------------------------------+
//| 2. FONCTION PRINCIPALE (À CHAQUE TICK)                           |
//+------------------------------------------------------------------+
void OnTick()
  {
   // --- A. GESTION DES ROLLOVERS ---
   if(EstEnZoneRoll())
     {
      if(PositionsTotal() > 0)
        {
         Print("⚠️ ZONE DE ROLLOVER : Fermeture d'urgence des positions !");
         FermerToutesLesPositions();
        }
      return;
     }

   // --- B. GESTION DU STOP SUIVEUR ---
   if(InpUseTrailing && PositionsTotal() > 0)
     {
      GererStopSuiveur();
     }

   // --- C. RECHERCHE DE SIGNAUX ---
   if(PositionsTotal() == 0)
     {
      if(CopyBuffer(maFastHandle, 0, 0, 3, maFastBuffer) <= 0) return;
      if(CopyBuffer(maSlowHandle, 0, 0, 3, maSlowBuffer) <= 0) return;

      double fast1 = maFastBuffer[1]; double fast2 = maFastBuffer[2];
      double slow1 = maSlowBuffer[1]; double slow2 = maSlowBuffer[2];

      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);

      // -- SIGNAL D'ACHAT --
      if(fast2 <= slow2 && fast1 > slow1)
        {
         double sl_price = ask * (1.0 - (InpSL_Pct / 100.0));
         double tp_price = InpUseTrailing ? 0 : ask * (1.0 + (InpTP_Pct / 100.0));

         sl_price = NormalizeDouble(sl_price, _Digits);
         tp_price = NormalizeDouble(tp_price, _Digits);

         double lot_size = CalculerTailleLot(ask, sl_price);
         trade.Buy(lot_size, _Symbol, ask, sl_price, tp_price, "Achat MA Cross");
        }

      // -- SIGNAL DE VENTE --
      else if(fast2 >= slow2 && fast1 < slow1)
        {
         double sl_price = bid * (1.0 + (InpSL_Pct / 100.0));
         double tp_price = InpUseTrailing ? 0 : bid * (1.0 - (InpTP_Pct / 100.0));

         sl_price = NormalizeDouble(sl_price, _Digits);
         tp_price = NormalizeDouble(tp_price, _Digits);

         double lot_size = CalculerTailleLot(bid, sl_price);
         trade.Sell(lot_size, _Symbol, bid, sl_price, tp_price, "Vente MA Cross");
        }
     }
  }

//+------------------------------------------------------------------+
//| HELPER : CALCUL MATHÉMATIQUE DU LOT SELON LE RISQUE              |
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

//+------------------------------------------------------------------+
//| HELPER : FERMER TOUTES LES POSITIONS                             |
//+------------------------------------------------------------------+
void FermerToutesLesPositions()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong ticket = PositionGetTicket(i);
      if(PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagicNumber)
        {
         trade.PositionClose(ticket);
        }
     }
  }

//+------------------------------------------------------------------+
//| HELPER : GESTION DU STOP SUIVEUR EN %                            |
//+------------------------------------------------------------------+
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
              {
               trade.PositionModify(ticket, new_sl, 0);
              }
           }
         else if(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_SELL)
           {
            double new_sl = NormalizeDouble(current_price + distance, _Digits);
            if((new_sl < current_sl && current_sl != 0) || current_sl == 0)
              {
               trade.PositionModify(ticket, new_sl, 0);
              }
           }
        }
     }
  }

//+------------------------------------------------------------------+
//| HELPER : LECTURE DU FICHIER CSV DES ROLLS                        |
//+------------------------------------------------------------------+
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

//+------------------------------------------------------------------+
//| HELPER : VÉRIFICATION ZONE DE ROLLOVER                           |
//+------------------------------------------------------------------+
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

//+------------------------------------------------------------------+
//| HELPER : SNAPSHOT DE L'ÉQUITÉ (appelé après chaque trade fermé)  |
//+------------------------------------------------------------------+
void PushEquitySnapshot()
  {
   ArrayResize(g_equity_curve, g_equity_count + 1);
   g_equity_curve[g_equity_count++] = AccountInfoDouble(ACCOUNT_EQUITY);
  }

//+------------------------------------------------------------------+
//| EVENT : DÉTECTION DE LA FERMETURE D'UN TRADE                     |
//+------------------------------------------------------------------+
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
     {
      PushEquitySnapshot();
     }
  }

//+------------------------------------------------------------------+
//| OPTIMIZER SCORE (régression linéaire sur la courbe d'équité)     |
//+------------------------------------------------------------------+
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
