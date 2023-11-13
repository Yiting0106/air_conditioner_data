import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import os


class DXPerfMap:

    def __init__(
            self,
            xlsx_file,
            sheet_ind,
            rated_To_db=35, #### 95 F = 35 C
            comp_sequences=1,
    ):

        self.xlsx_file = xlsx_file
        self.sheet_ind = sheet_ind
        self.rated_To_db = rated_To_db
        self.comp_sequences = comp_sequences

        self.df = self.load_xlsx()
        self.Te_db, self.Te_wb = self.load_AHRI_conditions(xlsx_file)
        self.df_rated, self.rated_capacity, self.df_rated_T, self.df_rated_OAT = self.get_rated_conditions(self.df)

    def load_xlsx(self):
        df = pd.read_excel(io=self.xlsx_file, sheet_name=self.sheet_ind)
        df["indoor_coil_entering_dry_bulb_temperature"] = self.convert_F_to_C(
            df["indoor_coil_entering_dry_bulb_temperature"])
        df["outdoor_coil_entering_dry_bulb_temperature"] = self.convert_F_to_C(
            df["outdoor_coil_entering_dry_bulb_temperature"])
        df["indoor_coil_entering_wet_bulb_temperature"] = self.convert_F_to_C(
            df["indoor_coil_entering_wet_bulb_temperature"])
        return df

    @staticmethod
    
    def convert_F_to_C(F):
        return (F-32) * 5/9

    ## have changed to DX Equipment's
    def load_AHRI_conditions(self, xlsx_file):
        # if xlsx_file == "./data/processed/DX_Equipment_Data_Collection_C_SubCool.xlsx":
        #     Te_db = 19.4 # 67 F
        #     Te_wb = 13.9 # 57 F
        # else:
        #     Te_db = 26.7 # 80 F
        #     Te_wb = 19.4 # 67 F
        
        Te_db = 26.7 # 80 F
        Te_wb = 19.4 # 67 F

        return Te_db, Te_wb

    def get_rated_conditions(self, df):
        T_db = df["indoor_coil_entering_dry_bulb_temperature"].values
        T_wb = df["indoor_coil_entering_wet_bulb_temperature"].values
        dist = (T_db - self.Te_db)**2 + (T_wb - self.Te_wb)**2
        # check the location of minimum distance
        min_idx = np.argmin(dist)
        df_rated = self.df.iloc[min_idx]
        rated_capacity = df_rated["gross_total_capacity"]
        # get rated capacity
        self.df["cap_f_t"] = self.df["gross_total_capacity"]/rated_capacity
        self.df["ff"] = self.df["outdoor_coil_entering_dry_bulb_temperature"]/self.rated_To_db
        # check the compressor stage
        stage_len = len(np.unique(self.df["compressor_sequence_number"].values))

        ##Get the dataframe for cap-f-t
        if self.comp_sequences == 1 or stage_len == 1: # compressor stage = 1 or 2 only
            df_const_T = self.df[
                (np.abs(self.df["indoor_coil_entering_dry_bulb_temperature"] - self.Te_db) < 1.0) &
                (np.abs(self.df["indoor_coil_entering_wet_bulb_temperature"] - self.Te_wb) < 1.0)
            ]

            #get the dataframe
            df_rated_OAT = self.df[(np.abs(self.df["outdoor_coil_entering_dry_bulb_temperature"] - self.rated_To_db) < 1.0)]
        else:
            df_const_T = dict()
            df_rated_OAT = dict()
            for num_comp in range(self.comp_sequences):
                _df = self.df.loc[self.df["compressor_sequence_number"] == (num_comp+1)]
                df_const_T[f"comp_seq_{num_comp+1}"] =  _df[
                (np.abs(_df["indoor_coil_entering_dry_bulb_temperature"] - self.Te_db) < 1.0) &
                (np.abs(_df["indoor_coil_entering_wet_bulb_temperature"] - self.Te_wb) < 1.0)
             ]
                df_rated_OAT[f"comp_seq_{num_comp+1}"] = _df[
                    (np.abs(_df["outdoor_coil_entering_dry_bulb_temperature"] - self.rated_To_db) < 1.0)]
        return df_rated, rated_capacity, df_const_T, df_rated_OAT



class CurveFit:

    def __init__(self, xlsx_file, x, targets, fun="bi-quad", y=None):
        self.xlsx_file = xlsx_file
        self.x = x
        self.y = y
        self.targets = targets
        self.function = fun

        if self.function == "bi-quad":
            self.X = self.f_biquad()
        elif self.function == "cubic":
            self.X = self.f_cubic()
        else:
            self.X = None

        assert self.X is not None
        self.coeffs = None

    def f_biquad(self):
        assert self.y is not None
        X = np.vstack(
            (
                np.ones(self.x.shape[0], ),
                self.x,
                self.x ** 2,
                self.y,
                self.y ** 2,
                np.multiply(self.x, self.y),
            )
        )

        return np.transpose(X)

    def f_cubic(self):
        X = np.vstack(
            (
                np.ones(self.x.shape[0], ),
                self.x,
                self.x ** 2,
                self.x ** 3,
            )
        )

        return np.transpose(X)

    def fit(self):
        coeffs = np.linalg.lstsq(self.X, self.targets)
        self.coeffs = coeffs[0]
        return self.coeffs

    def plot(self, file_str, sheet_ind='Table 1', label="Cap-f-t"):
        """
        Method to compare the predicted and
        """
        # Find the index of "./data/" and ".xlsx"
        xlsx_file = self.xlsx_file
        start_index = xlsx_file.find("./data/DX_Equipment_Data_Collection_") + len("./data/DX_Equipment_Data_Collection_")
        end_index = xlsx_file.find(".xlsx")
        # Extract the information between "./data/" and ".xlsx"
        extracted_info = xlsx_file[start_index:end_index]
        fig_dir = "./figures_OAT/" + extracted_info + "_" + sheet_ind + "/"

        #create directory
        if not os.path.exists(fig_dir):
            os.makedirs(fig_dir)
        assert self.coeffs is not None
        predictions = np.matmul(self.X, self.coeffs)
        print(f"The Pearson coefficient is : {np.corrcoef(self.targets, predictions)}")

        #plot and get the R^2 metric
        plt.plot(self.targets, predictions, 'ko')
        plt.plot(self.targets, self.targets, 'k-')
        plt.xlabel(f"{label} (Actual)", fontsize=16)
        plt.ylabel(f"{label} (Predictions)", fontsize=16)
        plt.savefig(os.path.join(fig_dir, f"{file_str}_R2_{np.corrcoef(self.targets, predictions)[0, 1]}_fit.png"))

        return None

def plot(xlsx_file, sheet_ind="Table 1"):
    # Find the index of "./data/" and ".xlsx"
    start_index = xlsx_file.find("./data/DX_Equipment_Data_Collection_") + len("./data/DX_Equipment_Data_Collection_")
    end_index = xlsx_file.find(".xlsx")
    # Extract the information between "./data/" and ".xlsx"
    extracted_info = xlsx_file[start_index:end_index]
    
    fig_dir = "./figures_OAT/" + extracted_info + "_" + sheet_ind + "/"
    df = pd.read_excel(io=xlsx_file, sheet_name=sheet_ind)
    #df.columns = df.index
    #Define grid variables
    x_cols = [
        "outdoor_coil_entering_dry_bulb_temperature",
        "indoor_coil_entering_wet_bulb_temperature",
        "indoor_coil_entering_dry_bulb_temperature",
        "indoor_coil_air_mass_flow_rate",
        "compressor_sequence_number"
    ]

    #define lookup variables
    y_cols = [
        "gross_total_capacity",
        "gross_sensible_capacity",
        "gross_power"
    ]

    #create directory
    if not os.path.exists(fig_dir):
        os.makedirs(fig_dir)

    for yc in y_cols:
        for xc in x_cols:
            plt.plot(df[xc], df[yc], 'ko')
            plt.xlabel(xc, fontsize=16)
            plt.ylabel(yc, fontsize=16)
            plt.savefig(os.path.join(fig_dir, f"filename_{yc}_vs_{xc}.png"))
            plt.close()

    return None


# run all
def run_all(xlsx_file,sheet_ind,num_comp_sequences,rated_To_db):
    DX = DXPerfMap(xlsx_file=xlsx_file, sheet_ind=sheet_ind,
                    rated_To_db=rated_To_db,comp_sequences=num_comp_sequences)
    plot(xlsx_file, sheet_ind)
    #test ff
    for nc in range(num_comp_sequences):
        if num_comp_sequences == 1:
            df_rated_OAT = DX.df_rated_OAT
        else:
            df_rated_OAT = DX.df_rated_OAT[f"comp_seq_{nc+1}"]
        TotCapTFit = CurveFit(xlsx_file,
            x=df_rated_OAT["outdoor_coil_entering_dry_bulb_temperature"].values,
            targets=df_rated_OAT["cap_f_t"].values,
            y=df_rated_OAT["indoor_coil_entering_wet_bulb_temperature"].values
        )
        #print("Curve fitting for Case I")
        TotCapTFit.fit()
        TotCapTFit.plot(file_str=f"TotCapFlowTempFit_seq_{nc+1}", sheet_ind=DX.sheet_ind)

        # ####New Curve fit objects
        if num_comp_sequences == 1:
            df_rated_T = DX.df_rated_T
        else:
            df_rated_T = DX.df_rated_T[f"comp_seq_{nc+1}"]
        TotCapFlowFit = CurveFit(xlsx_file,
            x=df_rated_T["ff"].values,
            targets=df_rated_T["cap_f_t"].values,
            fun="cubic"
        )
        # print("Curve Fitting for Case II")
        TotCapFlowFit.fit()
        TotCapFlowFit.plot(file_str=f"TotCapFlowFit_seq_{nc+1}", sheet_ind=DX.sheet_ind, label="Cap-f-ff")

    print(f"{xlsx_file}{sheet_ind} runned succefully.")

    return

if __name__ == "__main__":

#     ### 1. DX_Equipment_Data_Collection_D.xlsx
#     xlsx_file = "./data/processed/DX_Equipment_Data_Collection_D.xlsx"

#     ## manually run to check each table to get 'num_comp_sequences' and 'flow_rate'
    
#         # Table 1
#     sheet_ind = "Table 1"
#     num_comp_sequences = 1 # 1 compressor
#     run_all(xlsx_file,sheet_ind,num_comp_sequences,35)

#         # Table 2
#     sheet_ind = "Table 2"
#     num_comp_sequences = 1 # 2 compressors
#     run_all(xlsx_file,sheet_ind,num_comp_sequences,35)

#         # Table 3
#     sheet_ind = "Table 3"
#     num_comp_sequences = 1 # 2 compressors
#     run_all(xlsx_file,sheet_ind,num_comp_sequences,35)

#         # Table 4
#     sheet_ind = "Table 4"
#     num_comp_sequences = 1 # 2 compressors
#     run_all(xlsx_file,sheet_ind,num_comp_sequences,35)

#         # Table 5
#     sheet_ind = "Table 5"
#     num_comp_sequences = 1 # 2 compressors
#     run_all(xlsx_file,sheet_ind,num_comp_sequences,35)

#         # Table 6
#     sheet_ind = "Table 6"
#     num_comp_sequences = 1 # 3 compressors
#     run_all(xlsx_file,sheet_ind,num_comp_sequences,35)

#         # Table 7
#     sheet_ind = "Table 7"
#     num_comp_sequences = 1 # 4 compressors
#     run_all(xlsx_file,sheet_ind,num_comp_sequences,35)   

#         # Table 8
#     sheet_ind = "Table 8"
#     num_comp_sequences = 1 # 5 compressors
#     run_all(xlsx_file,sheet_ind,num_comp_sequences,35)

# ### 2. DX_Equipment_Data_Collection_L.xlsx
#     xlsx_file = "./data/processed/DX_Equipment_Data_Collection_L.xlsx"

#     ## manually run to check each table to get 'num_comp_sequences' and 'flow_rate'
#         # Table 1
#     sheet_ind = "Table 1"
#     num_comp_sequences = 1 # 1 compressor
#     run_all(xlsx_file,sheet_ind,num_comp_sequences,35)

#         # Table 2
#     sheet_ind = "Table 2"
#     num_comp_sequences = 3
#     run_all(xlsx_file,sheet_ind,num_comp_sequences,35)

#         # Table 3
#     sheet_ind = "Table 3"
#     num_comp_sequences = 3
#     run_all(xlsx_file,sheet_ind,num_comp_sequences,35)

#         # Table 4
#     sheet_ind = "Table 4"
#     num_comp_sequences = 4
#     run_all(xlsx_file,sheet_ind,num_comp_sequences,35)

#         # Table 5
#     sheet_ind = "Table 5"
#     num_comp_sequences = 4
#     run_all(xlsx_file,sheet_ind,num_comp_sequences,35)

#         # Table 6
#     sheet_ind = "Table 6"
#     num_comp_sequences = 4
#     run_all(xlsx_file,sheet_ind,num_comp_sequences,35)

#         # Table 7
#     sheet_ind = "Table 7"
#     num_comp_sequences = 2
#     run_all(xlsx_file,sheet_ind,num_comp_sequences,35)

#         # Table 8
#     sheet_ind = "Table 8"
#     num_comp_sequences = 2
#     run_all(xlsx_file,sheet_ind,num_comp_sequences,35)

#         # Table 9
#     sheet_ind = "Table 9"
#     num_comp_sequences = 2
#     run_all(xlsx_file,sheet_ind,num_comp_sequences,35)

#         # Table 10
#     sheet_ind = "Table 10"
#     num_comp_sequences = 2
#     run_all(xlsx_file,sheet_ind,num_comp_sequences,35)

# ### 3. DX_Equipment_Data_Collection_C_SM.xlsx
#     xlsx_file = "./data/processed/DX_Equipment_Data_Collection_C_SM.xlsx"

#     ## manually run to check each table to get 'num_comp_sequences' and 'flow_rate'
#         # Table 1-8, 10
#     sheet_inds = ["Table 1","Table 2","Table 3","Table 4","Table 5","Table 6","Table 7","Table 8","Table 10"]
#     for sheet_ind in sheet_inds:
#         num_comp_sequences = 1 # 1 compressor
#         run_all(xlsx_file,sheet_ind,num_comp_sequences,35)
    
#         # Table 9, 11-18
#     sheet_inds = ["Table 9","Table 11","Table 12","Table 13","Table 14","Table 15","Table 16","Table 17","Table 18",]
#     for sheet_ind in sheet_inds:
#         num_comp_sequences = 2
#         run_all(xlsx_file,sheet_ind,num_comp_sequences,35)

### 4. DX_Equipment_Data_Collection_C_SubCool.xlsx
    xlsx_file = "./data/processed/DX_Equipment_Data_Collection_C_SubCool.xlsx"

    ## manually run to check each table to get 'num_comp_sequences' and 'flow_rate'
        # Table 1-8, 10
    sheet_inds = ["Table 1","Table 2","Table 3","Table 4","Table 5","Table 6","Table 7","Table 8","Table 10"]
    for sheet_ind in sheet_inds:
        num_comp_sequences = 1 # 1 compressor
        run_all(xlsx_file,sheet_ind,num_comp_sequences,35)
    
        # Table 9, 11-18
    sheet_inds = ["Table 9","Table 11","Table 12","Table 13","Table 14","Table 15","Table 16","Table 17","Table 18",]
    for sheet_ind in sheet_inds:
        num_comp_sequences = 2
        run_all(xlsx_file,sheet_ind,num_comp_sequences,35)
