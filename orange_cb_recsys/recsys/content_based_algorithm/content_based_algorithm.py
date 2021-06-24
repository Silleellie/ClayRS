import abc
from typing import List
import pandas as pd
from scipy.sparse import hstack
from sklearn.exceptions import NotFittedError
from sklearn.feature_extraction import DictVectorizer
from sklearn.utils.validation import check_is_fitted
import numpy as np

from orange_cb_recsys.recsys.algorithm import Algorithm

from orange_cb_recsys.content_analyzer.content_representation.content import Content


class ContentBasedAlgorithm(Algorithm):
    """
    Abstract class for the content-based algorithms

    Like every subclass of Algorithm, it must implements the 'initialize(...)' method where one must pass
    important parameters for the usage of this specific type of Algorithm

    Said method must be called right after the instantiation of the Algorithm

    Args:
    item_field (dict): dict where the key is the name of the field
        that contains the content to use, value is the representation(s) that will be
        used for the said item. The value of a field can be a string or a list,
        use a list if you want to use multiple representations for a particular field.
        Check the example above for more.
    threshold (float): Threshold for the ratings. If the rating is greater than the threshold, it will be considered
        as positive
    """

    def __init__(self, item_field: dict, threshold: float):
        self.item_field: dict = self._bracket_representation(item_field)
        self.threshold: float = threshold
        self.__transformer = DictVectorizer(sparse=True, sort=False)

    @staticmethod
    def _bracket_representation(item_field: dict):
        """
        Private method that brackets every representation in case the user passed a string
        instead of a list.

        EXAMPLE::
            > item_field = {'Plot': '0', 'Genre': ['0', '1']}
            > print(_bracket_representation(item_field))

            > {'Plot': ['0'], 'Genre': ['0', '1']}

        Args:
            item_field (dict): dict that may contain values that need to be bracketed

        Returns:
            The item_field passed with all values inside a list
        """
        for field in item_field:
            if isinstance(item_field[field], str):
                item_field[field] = [item_field[field]]

        return item_field

    @staticmethod
    def _calc_mean_user_threshold(user_ratings: pd.DataFrame):
        return user_ratings['score'].mean()

    def extract_features_item(self, item: Content):
        """
        Function that extracts the feature of a loaded item using the item_field parameter passed in the
        constructor.

        It extracts only the chosen representations of the chosen fields in the item loaded
        EXAMPLE:

            with item_field = {'Plot': ['0'], 'Genre': ['0', '1']}, the function will extracts
            only the representation with the '0' id for the field 'Plot' and both the representations
            with '0' and '1' id for the field 'Genre'

        Args:
            item (Content): item loaded of which we need to extract its feature

        Returns:
            A list containing all representations extracted for the item
        """
        item_bag_list = []
        if item is not None:
            for field in self.item_field:
                field_representations = self.item_field[field]

                for representation in field_representations:
                    item_bag_list.append(
                        item.get_field(field).get_representation(representation).value
                    )

        return item_bag_list

    def fuse_representations(self, X: list):
        """
        Transform the X passed vectorizing if X contains dicts and merging
        multiple representations in a single one for every item in X.
        So if X = [
                    [dict, arr, arr]
                        ...
                    [dict, arr, arr]
                ]
        where every sublist contains multiple representation for a single item,
        the function returns:
        X = [
                arr,
                ...
                arr
            ]
        Where every row is the fused representation for the item

        Args:
            X (list): list that contains representations of the items

        Returns:
            X fused and vectorized
        """

        # We check if there are dicts as representation in the first element of X,
        # since the representations are the same for all elements in X we can check
        # for dicts only in one element
        need_vectorizer = any(isinstance(rep, dict) for rep in X[0])

        if need_vectorizer:
            # IF the transformer is not fitted then we are training the model
            try:
                check_is_fitted(self.__transformer)
            except NotFittedError:
                X_dicts = []
                for item in X:
                    for rep in item:
                        if isinstance(rep, dict):
                            X_dicts.append(rep)

                self.__transformer.fit(X_dicts)

            # In every case, we transform the input
            X_vectorized = []
            for sublist in X:
                single_list = []
                for item in sublist:
                    if isinstance(item, dict):
                        vector = self.__transformer.transform(item)
                        single_list.append(vector)
                    else:
                        single_list.append(item)
                X_vectorized.append(single_list)
        else:
            X_vectorized = X

        try:
            X_sparse = [hstack(sublist).toarray().flatten() for sublist in X_vectorized]
        except ValueError:
            X_sparse = [np.column_stack(sublist).flatten() for sublist in X_vectorized]

        return X_sparse

    @abc.abstractmethod
    def process_rated(self, user_ratings: pd.DataFrame, items_directory: str):
        """
        Abstract method that processes rated items for the user.

        Every content-based algorithm processes rated items differently, it may be needed to extract features
        from the rated items and label them, extract features only from the positive ones, etc.

        The rated items processed must be stored into a private attribute of the algorithm, later used
        by the fit() method.

        Args:
            user_ratings (pd.DataFrame): DataFrame containing ratings of a single user
            items_directory (str): path of the directory where the items are stored
        """
        raise NotImplementedError

    @abc.abstractmethod
    def fit(self):
        """
        Abstract method that fits the content-based algorithm.

        Every content based algorithm has a different fit process, it may be needed to fit a classifier,
        to build the centroid of the positive items, to build a query for the index, etc.

        It must be called after the the process_rated() method since it uses private attributes calculated
        by said method to fit the algorithm.

        The fitted object will also be stored in a private attribute.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def predict(self, user_ratings: pd.DataFrame, items_directory: str,
                filter_list: List[str] = None) -> pd.DataFrame:
        """
        |  Abstract method that predicts how much a user will like unrated items
        |  If the algorithm is not a PredictionScore Algorithm, implement this method like this:

        def predict():
            raise NotPredictionAlg

        One can specify which items must be predicted with the filter_list parameter,
        in this case ONLY items in the filter_list will be predicted.
        One can also pass items already seen by the user with the filter_list parameter.
        Otherwise, ALL unrated items will be predicted.

        Args:
            user_ratings (pd.DataFrame): DataFrame containing ratings of a single user
            items_directory (str): path of the directory where the items are stored
            filter_list (list): list of the items to predict, if None all unrated items will be predicted
        Returns:
            pd.DataFrame: DataFrame containing one column with the items name,
                one column with the score predicted
        """
        raise NotImplementedError

    @abc.abstractmethod
    def rank(self, user_ratings: pd.DataFrame, items_directory: str, recs_number: int = None,
             filter_list: List[str] = None) -> pd.DataFrame:
        """
        |  Rank the top-n recommended items for the user. If the recs_number parameter isn't specified,
        |  All items will be ranked.
        |  If the algorithm is not a Ranking Algorithm, implement this method like this:

        def predict():
            raise NotRankingAlg

        One can specify which items must be ranked with the filter_list parameter,
        in this case ONLY items in the filter_list will be used to calculate the rank.
        One can also pass items already seen by the user with the filter_list parameter.
        Otherwise, ALL unrated items will be used to calculate the rank.

        Most of the time the rank is calculated by calling the predict() method and sorting the ratings
        predicted, but it's abstract since some algorithm may implement some optimizations to calculate
        the rank.

        Args:
            user_ratings (pd.DataFrame): DataFrame containing ratings of a single user
            items_directory (str): path of the directory where the items are stored
            recs_number (int): number of the top items that will be present in the ranking
            filter_list (list): list of the items to rank, if None all unrated items will be used to
                calculate the rank
        Returns:
            pd.DataFrame: DataFrame containing one column with the items name,
                one column with the rating predicted, sorted in descending order by the 'rating' column
        """
        raise NotImplementedError

    # @Handler_EmptyFrame
    # def fit_predict(self, user_id: str, filter_list: List[str] = None):
    #     """
    #     Method used to predict the rating of the user passed for all unrated items or for the items passed
    #     in the filter_list parameter.
    #
    #     The method fits the algorithm and then calculates the prediction
    #
    #     Args:
    #         user_id (str): user_id of the user
    #         filter_list (list): list of the items to rank, if None all unrated items will be used to
    #             calculate the rank
    #     Returns:
    #         pd.DataFrame: DataFrame containing one column with the items name,
    #             one column with the rating predicted
    #     """
    #     # Extracts ratings of the user
    #     user_ratings = self.ratings[self.ratings['from_id'] == user_id]
    #
    #     # Process rated items
    #     self.process_rated(user_ratings, self.items_directory)
    #
    #     # Fit
    #     self.fit()
    #
    #     # Predict
    #     prediction = self.predict(user_ratings, self.items_directory, filter_list)
    #     return prediction
    #
    # @Handler_EmptyFrame
    # def fit_rank(self, user_id: str, recs_number: int = None, filter_list: List[str] = None):
    #     """
    #     Method used to rank for a particular user all unrated items or the items specified in
    #     the filter_list parameter.
    #
    #     The method fits the algorithm and then calculates the rank.
    #
    #     If the recs_number is specified, then the rank will contain the top-n items for the user.
    #
    #     Args:
    #         user_id (str): user_id of the user
    #         recs_number (int): number of the top items that will be present in the ranking
    #         filter_list (list): list of the items to rank, if None all unrated items will be used to
    #             calculate the rank
    #     Returns:
    #         pd.DataFrame: DataFrame containing one column with the items name,
    #             one column with the rating predicted, sorted in descending order by the 'rating' column
    #     """
    #     # Extracts ratings of the user
    #     user_ratings = self.ratings[self.ratings['from_id'] == user_id]
    #
    #     # Process rated items
    #     self.process_rated(user_ratings, self.items_directory)
    #
    #     # Fit
    #     self.fit()
    #
    #     # Rank
    #     rank = self.rank(user_ratings, self.items_directory, recs_number, filter_list)
    #     return rank
